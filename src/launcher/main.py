import sys
import os
import ctypes
import threading
import time
import math
import json
import colorsys
import shutil
import subprocess

# ㅕㅑ
try:
	import pystray
	from PIL import Image, ImageDraw
except Exception:
	pystray = None

try:
	import tkinter as tk
	from tkinter.scrolledtext import ScrolledText
except Exception:
	tk = None


def load_ascii_banner_text():
	"""Load ascii.txt from common locations; always return raw text.

	We keep the ASCII art in a single file (ascii.txt) and only change colors.
	"""
	candidates = []
	if getattr(sys, "_MEIPASS", None):
		candidates.append(os.path.join(sys._MEIPASS, "ascii.txt"))
	here = os.path.abspath(os.path.dirname(__file__))
	candidates.append(os.path.join(here, "ascii.txt"))
	candidates.append(os.path.join(os.getcwd(), "ascii.txt"))

	for p in candidates:
		try:
			with open(p, "r", encoding="utf-8") as f:
				return f.read()
		except Exception:
			continue

	# fallback to bundled ascii_art module
	try:
		repo_src = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
		if repo_src not in sys.path:
			sys.path.insert(0, repo_src)
		from utils import ascii_art

		return ascii_art.get_banner("idle")
	except Exception:
		return "MANTA Anti-Virus\n"


# --- State manager -------------------------------------------------
class StateManager:
	def __init__(self):
		self._lock = threading.Lock()
		self._state = "idle"
		self._msg = "Ready"

	def set(self, state: str, msg: str = ""):
		with self._lock:
			self._state = state
			self._msg = msg

	def get(self):
		with self._lock:
			return self._state, self._msg


STATE = StateManager()

# store last scanner results for quarantine action
LAST_SCAN_RESULTS = None
LOGS = []
INPUT_ACTIVE = threading.Event()
GUI_VISIBLE = threading.Event()
TRAY_ICON = None
scanner = None
monitor = None
CONSOLE_HANDLER = None
BANNER_TEXT = None


def load_local_hash_db():
	"""Load local virus DB of hashes from repo root file 'virus_db.txt'.

	Lines may be plain hex or 'sha256:<hex>'. Return set of lowercase hex strings.
	"""

	# Prefer db/virus_db.txt (repo db folder). Fall back to top-level virus_db.txt for
	# backwards compatibility.
	db_dir = os.path.join(os.getcwd(), "db")
	db_path = os.path.join(db_dir, "virus_db.txt")
	if not os.path.isfile(db_path):
		# fallback to legacy location
		alt = os.path.join(os.getcwd(), "virus_db.txt")
		if os.path.isfile(alt):
			db_path = alt
	hashes = set()
	try:
		with open(db_path, "r", encoding="utf-8") as f:
			for line in f:
				s = line.strip()
				if not s:
					continue
				if s.lower().startswith("sha256:"):
					s = s.split(":", 1)[1].strip()
				# basic validation: 64 hex chars
				if len(s) == 64:
					hashes.add(s.lower())
	except Exception:
		pass
	return hashes


def check_hash_db_and_mark(parsed):
	"""Mark STATE threat if any file hash matches local DB. Also annotate LAST_SCAN_RESULTS entries."""
	if not parsed:
		return
	db = load_local_hash_db()
	if not db:
		return
	found = 0
	for f in parsed.get("files", []):
		sha = f.get("sha256")
		if sha and sha.lower() in db:
			found += 1
			# annotate in LAST_SCAN_RESULTS if present
			try:
				if LAST_SCAN_RESULTS and isinstance(LAST_SCAN_RESULTS, dict):
					for lf in LAST_SCAN_RESULTS.get("files", []):
						if lf.get("path") == f.get("path"):
							lf["matched_db"] = True
			except Exception:
				pass
	if found > 0:
		STATE.set("threat", f"Local DB: {found} hash matches")


def save_local_hash_db(hashes):
	"""Atomically save set of hashes to db/virus_db.txt in repo root."""
	db_dir = os.path.join(os.getcwd(), "db")
	os.makedirs(db_dir, exist_ok=True)
	db_path = os.path.join(db_dir, "virus_db.txt")
	try:
		tmp = db_path + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			for h in sorted(hashes):
				f.write(f"sha256: {h}\n")
		os.replace(tmp, db_path)
		return True
	except Exception:
		return False


# --- Color helpers -------------------------------------------------
def palette_for_state(state: str, position_ratio: float, phase: float):
	"""Return an (R,G,B) color for given state and normalized position [0,1].

	position_ratio: horizontal position in line
	phase: animation phase 0..1
	"""
	# make transitions more subtle: lower saturation and smaller hue offsets
	# small global brighten: increase value slightly for all states
	if state == "idle":
		# 바다 느낌: 청록-파랑 계열, 채도은은하게, 명도 조금 올림
		base_h = 0.53  # 청록-파랑
		sat = 0.5
		val = 0.98
	elif state == "scanning":
		base_h = 0.45  # 더 푸른-청록
		sat = 0.55
		val = 0.98
	elif state == "threat":
		base_h = 0.02  # red-orange
		sat = 0.65
		val = 0.93
	elif state == "deleting":
		base_h = 0.02
		sat = 0.5
		val = 0.82
	else:
		base_h = 0.0
		sat = 0.45
		val = 0.93

	# For a consistent sweep effect across the whole banner, ignore per-position
	# hue offsets and compute a single hue that slowly drifts with phase.
	# phase in 0..1 controls a small hue_range so color changes are subtle and smooth.
	hue_range = 0.06  # how far hue drifts from base_h
	hue = (base_h + (phase - 0.5) * hue_range) % 1.0
	# gentle pulsing on value only, keep saturation steady to avoid rainbow look
	val = max(0.0, min(1.0, val + math.sin(phase * math.tau) * 0.01))
	r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
	return int(r * 255), int(g * 255), int(b * 255)


def vertical_gradient_color(line_index: int, total_lines: int, phase: float = 0.0):
	"""Return an RGB color for a given line index using a vertical gradient.

	This uses a linear interpolation similar to the snippet you showed:
	  bg_r = int(10 - (10 * bg_ratio))
	  bg_g = int(20 - (20 * bg_ratio))
	  bg_b = int(45 - (35 * bg_ratio))

	We add a tiny phase-based modulation to make the gradient gently animate.
	"""
	if total_lines <= 1:
		bg_ratio = 0.0
	else:
		bg_ratio = float(line_index) / float(total_lines - 1)

	# 밝고 청명한 파랑에서 맨 아래 몇 줄만 흰색에 가깝게 떨어지는 그라데이션
	# 시작은 살짝 밝은 바다색, 끝은 거의 흰색 직전 색
	start_r, start_g, start_b = 40.0, 140.0, 200.0  # 밝은 청-시안 계열
	mid_r, mid_g, mid_b = 220.0, 240.0, 250.0     # 화이트 전 단계
	# 마지막 white_band 줄은 완전한 화이트로 처리
	white_band = max(1, min(4, int(total_lines * 0.08)))

	# if within white band, return near-white (with tiny shimmer)
	if line_index >= total_lines - white_band:
		try:
			mod = int(math.sin(phase * math.tau) * 2)
		except Exception:
			mod = 0
		w = max(230, min(255, 255 + mod))
		return w, w, w

	# otherwise interpolate from start -> mid across the non-white region
	usable = max(1, total_lines - white_band)
	ratio = float(line_index) / float(usable - 1)
	r = int(start_r + (mid_r - start_r) * ratio)
	g = int(start_g + (mid_g - start_g) * ratio)
	b = int(start_b + (mid_b - start_b) * ratio)

	# subtle phase shimmer on brightness
	try:
		mod = int(math.sin(phase * math.tau) * 2)
	except Exception:
		mod = 0
	r = max(0, min(255, r + mod))
	g = max(0, min(255, g + mod))
	b = max(0, min(255, b + mod))
	return r, g, b


# --- Terminal renderer ---------------------------------------------
def terminal_renderer(banner_text: str, stop_event: threading.Event):
	# Animate banner with a moving gradient. Pause animation while user is typing
	# banner_text may be updated at runtime via BANNER_TEXT global.
	# We recompute lines each frame so changes (reset) are reflected immediately.
	lines = banner_text.splitlines() if banner_text else []
	if not lines and BANNER_TEXT:
		lines = BANNER_TEXT.splitlines()
	if not lines:
		return
	width = max(len(l) for l in lines)
	fps = 30
	delay = 1.0 / fps
	try:
		while not stop_event.is_set():
			# if GUI is visible, prefer GUI rendering; skip console redraw
			if GUI_VISIBLE.is_set():
				time.sleep(0.05)
				continue
			# if user is typing, don't redraw (prevents prompt corruption)
			if INPUT_ACTIVE.is_set():
				time.sleep(0.05)
				continue

			state, msg = STATE.get()
			# refresh banner from global if updated
			cur = BANNER_TEXT if BANNER_TEXT else banner_text
			lines = cur.splitlines() if cur else []
			if not lines:
				time.sleep(0.2)
				continue
			out_lines = []
			for line in lines:
				row = []
				for x, ch in enumerate(line.ljust(width)):
					if ch.isspace():
						row.append(ch)
					else:
						pos = x / max(1, width - 1)
						# make phase vary very fast for continuous flowing effect
						tphase = (time.time() * 6.0 + pos * 4.0) % 1.0
						R, G, B = palette_for_state(state, pos, tphase)
						row.append(f"\x1b[38;2;{R};{G};{B}m{ch}\x1b[0m")
				out_lines.append(''.join(row))

			# redraw whole screen then print status and a prompt placeholder
			sys.stdout.write("\x1b[H\x1b[J")
			sys.stdout.write('\n'.join(out_lines) + "\n")
			sys.stdout.write(f"Status: {msg}\n")
			# show prompt indicator when not typing
			sys.stdout.write("manta> ")
			sys.stdout.flush()

			# use time-based phase for smooth continuous flow
			phase = (time.time() * 0.6) % 1.0
			time.sleep(delay)
	except Exception:
		pass


# --- GUI renderer (tkinter) ---------------------------------------
class GuiWindow:
	def __init__(self, banner_text: str):
		self.banner = banner_text
		self.root = None
		self.output = None
		self.entry = None
		self._running = False

	def start(self):
		if tk is None:
			return
		t = threading.Thread(target=self._run, daemon=True)
		t.start()

	def _run(self):
		self.root = tk.Tk()
		self.root.title("MANTA Launcher")
		try:
			self.root.wm_attributes("-alpha", 0.92)
		except Exception:
			pass
		# 상단: 고정 배너 영역 (스크롤되지 않음)
		lines = self.banner.splitlines()
		banner_height = max(3, min(20, len(lines)))
		self.banner_widget = tk.Text(self.root, wrap=tk.NONE, height=banner_height, font=("Consolas", 12), bg="#071017", fg="#cfe8ff", bd=0, highlightthickness=0)
		self.banner_widget.pack(fill=tk.X)
		self.banner_widget.configure(state=tk.DISABLED)

		# 중단: 출력 영역 (스크롤 가능)
		self.output = ScrolledText(self.root, wrap=tk.NONE, font=("Consolas", 12), bg="#071017", fg="#cfe8ff", bd=0)
		self.output.pack(fill=tk.BOTH, expand=True)
		self.output.configure(state=tk.DISABLED)

		# simple entry at bottom
		entry_frame = tk.Frame(self.root, bg="#071017")
		entry_frame.pack(fill=tk.X, side=tk.BOTTOM)
		self.entry = tk.Entry(entry_frame, font=("Consolas", 12), bg="#0b1416", fg="#cfe8ff")
		self.entry.pack(fill=tk.X, padx=6, pady=6, ipady=4)
		self.entry.bind('<Return>', self._on_entry_submit)

		# hide on close (keep tray behavior)
		try:
			self.root.protocol('WM_DELETE_WINDOW', self._on_close)
		except Exception:
			pass

		try:
			GUI_VISIBLE.set()
		except Exception:
			pass

		self._running = True
		self._update_loop()
		self.root.mainloop()

	def _update_loop(self):
		if not self._running:
			return
		state, msg = STATE.get()
		self._render(state, msg)
		if self.root:
			self.root.after(100, self._update_loop)

	def _render(self, state, msg):
		# 배너 위젯만 갱신: 배너는 고정된 위치에서 실시간 그라데이션으로 빛나도록 함
		try:
			lines = self.banner.splitlines()
			width = max(len(l) for l in lines) if lines else 0
			self.banner_widget.configure(state=tk.NORMAL)
			self.banner_widget.delete("1.0", tk.END)
			phase = (time.time() * 0.12) % 1.0
			# use vertical gradient per-line similar to user snippet
			for y, line in enumerate(lines):
				r, g, b = vertical_gradient_color(y, len(lines), phase)
				# apply same color across the whole line for 일관된 느낌
				hexcol = f"#{r:02x}{g:02x}{b:02x}"
				tag = f"line_{y}"
				if tag not in self.banner_widget.tag_names():
					try:
						self.banner_widget.tag_config(tag, foreground=hexcol)
					except Exception:
						pass
				try:
					self.banner_widget.insert(tk.END, line.ljust(width), tag)
				except Exception:
					self.banner_widget.insert(tk.END, line.ljust(width))
				self.banner_widget.insert(tk.END, "\n")
			# 상태는 배너 마지막 줄에 표시
			try:
				self.banner_widget.insert(tk.END, f"\nStatus: {msg}")
			except Exception:
				pass
			self.banner_widget.configure(state=tk.DISABLED)
		except Exception:
			pass

	def stop(self):
		if self.root:
			try:
				self.root.quit()
			except Exception:
				pass
		self._running = False

	def _on_close(self):
		# 사용자가 X를 누르면 창을 완전히 숨기되(작업표시줄에서 사라지게)
		# 트레이 아이콘은 유지되도록 한다. 트레이 아이콘이 아직 생성되지 않았다면
		# 가능한 경우 최소한의 트레이 아이콘을 생성한다.
		try:
			self.root.withdraw()
			GUI_VISIBLE.set()
			# ensure tray icon exists
			if TRAY_ICON is None and pystray is not None:
				try:
					img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
					d = ImageDraw.Draw(img)
					d.ellipse((4, 4, 60, 60), fill=(30, 144, 255, 255))
					def _show():
						try:
							self.root.deiconify()
							GUI_VISIBLE.clear()
						except Exception:
							pass
					def _exit():
						try:
							on_exit()
						except Exception:
							os._exit(0)
					menu = pystray.Menu(pystray.MenuItem("Show GUI", lambda _: _show()), pystray.MenuItem("Exit", lambda _: _exit()))
					icon = pystray.Icon("MANTA", img, "MANTA", menu)
					t = threading.Thread(target=icon.run, daemon=True)
					t.start()
					globals()['TRAY_ICON'] = icon
				except Exception:
					pass
		except Exception:
			pass

	def write_line(self, text: str):
		if not self.output:
			return
		try:
			self.output.configure(state=tk.NORMAL)
			self.output.insert(tk.END, text + "\n")
			self.output.see(tk.END)
			self.output.configure(state=tk.DISABLED)
		except Exception:
			pass

	def _on_entry_submit(self, event=None):
		try:
			cmd = self.entry.get().strip()
			if not cmd:
				return 'break'
			self.write_line(f"manta> {cmd}")
			self.entry.delete(0, tk.END)

			def _runner():
				try:
					INPUT_ACTIVE.set()
					process_command(cmd, writer=self.write_line)
				finally:
					INPUT_ACTIVE.clear()

			threading.Thread(target=_runner, daemon=True).start()
			return 'break'
		except Exception:
			return 'break'


# --- Tray icon -----------------------------------------------------
def create_tray(icon_title: str, on_show_gui, on_start_scan, on_stop_scan, on_quarantine, on_exit):
	if pystray is None:
		return None

	# simple icon: colored circle
	img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
	d = ImageDraw.Draw(img)
	d.ellipse((4, 4, 60, 60), fill=(30, 144, 255, 255))

	def menu_action(action):
		def _():
			action()
		return _

	menu = pystray.Menu(
		pystray.MenuItem("Show GUI", menu_action(on_show_gui)),
		pystray.MenuItem("Start Scan", menu_action(on_start_scan)),
		pystray.MenuItem("Stop Scan", menu_action(on_stop_scan)),
		pystray.MenuItem("Quarantine Findings", menu_action(on_quarantine)),
		pystray.MenuItem("Exit", menu_action(on_exit)),
	)
	icon = pystray.Icon(icon_title, img, icon_title, menu)
	t = threading.Thread(target=icon.run, daemon=True)
	t.start()
	global TRAY_ICON
	TRAY_ICON = icon
	return icon


# DLL helper 
def find_dist_dll(name):
	candidates = [os.path.join(os.getcwd(), "dist", name), os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), name), name]
	for p in candidates:
		if os.path.isfile(p):
			return p
	return None


def load_cdll(path):
	return ctypes.CDLL(os.path.abspath(path))


def recv_and_free(lib, cptr, free_name="FreeResult"):
	if not cptr:
		return None
	raw = ctypes.string_at(cptr)
	try:
		free_fn = getattr(lib, free_name)
		free_fn.argtypes = [ctypes.c_void_p]
		free_fn.restype = None
		free_fn(cptr)
	except Exception:
		pass
	try:
		return raw.decode("utf-8")
	except Exception:
		return raw.decode("utf-8", errors="replace")


def perform_scan_with_scanner(scanner, target_path: bytes = b"."):
	"""Call scanner.ScanPath and return parsed JSON (dict) or None.

	This helper centralizes FFI argument/return handling and sets STATE
	to 'threat' if suspicious files are reported.
	"""
	if scanner is None:
		return None
	try:
		scanner.ScanPath.argtypes = [ctypes.c_char_p]
		scanner.ScanPath.restype = ctypes.c_void_p
		scanner.FreeResult.argtypes = [ctypes.c_void_p]
		scanner.FreeResult.restype = None
		cptr = scanner.ScanPath(target_path)
		res = recv_and_free(scanner, cptr, free_name="FreeResult")
		if not res:
			return None
		try:
			parsed = json.loads(res)
			# If scanner reports suspicious items, set state.
			summary = parsed.get("summary", {})
			if summary.get("suspicious", 0) > 0:
				STATE.set("threat", f"Scanner found {summary.get('suspicious')} suspicious files")
			else:
				STATE.set("idle", "Scan complete — no suspicious files")
			# store last results for possible quarantine
			global LAST_SCAN_RESULTS
			LAST_SCAN_RESULTS = parsed
			# check local hash DB for matches (may update STATE)
			try:
				check_hash_db_and_mark(parsed)
			except Exception:
				pass
			return parsed
		except Exception:
			return None
	except Exception:
		return None


# --- Command processor (module-level so GUI/threads can call it)
def process_command(line, writer=print):
	parts = line.strip().split()
	if not parts:
		return
	cmd = parts[0].lower()
	args = parts[1:]

	def _w(s):
		try:
			writer(s)
		except Exception:
			print(s)

	if cmd in ('help', 'h', '?'):
		_w("Interactive commands: scan [path], scan-async, monitor start|stop, quarantine, db add <sha256>, db remove <sha256>, db list, status, logs, save-logs <file>, help, exit")
		return

	if cmd == 'scan':
		path = args[0] if args else '.'
		_w(f"Starting scan: {path}")
		res = perform_scan_with_scanner(scanner, path.encode('utf-8'))
		if res:
			summary = res.get('summary', {})
			_w(f"Scan complete. total={summary.get('total')} suspicious={summary.get('suspicious')}")
			for f in res.get('files', [])[:10]:
				if f.get('suspicious'):
					_w(f" - {f.get('path')} : reasons={f.get('suspicious_reasons')}")
		else:
			_w('Scan failed or no result')
		return

	if cmd in ('scan-async', 'start-scan'):
		def _scan():
			STATE.set('scanning', 'Scanning (async)')
			if scanner is not None and hasattr(scanner, 'ScanPath'):
				try:
					scanner.ScanPath.argtypes = [ctypes.c_char_p]
					scanner.ScanPath.restype = ctypes.c_void_p
					scanner.FreeResult.argtypes = [ctypes.c_void_p]
					scanner.FreeResult.restype = None
					cptr = scanner.ScanPath(b'.')
					res = recv_and_free(scanner, cptr, free_name='FreeResult')
					if res:
						try:
							j = json.loads(res)
							if j.get('files'):
								STATE.set('threat', f"Found {len(j.get('files'))} items")
								return
						except Exception:
							pass
				except Exception:
					pass
			STATE.set('idle', 'Scan complete')

		threading.Thread(target=_scan, daemon=True).start()
		return

	if cmd == 'monitor':
		if not args:
			_w('Usage: monitor start|stop')
			return
		arg = args[0].lower()
		if monitor is None:
			_w('Monitor module not loaded')
			return
		if arg == 'start':
			try:
				monitor.MonitorStart()
				STATE.set('idle', 'Monitor started')
				_w('Monitor started')
			except Exception as e:
				_w(f'Failed to start monitor: {e}')
		elif arg == 'stop':
			try:
				monitor.MonitorStop()
				STATE.set('idle', 'Monitor stopped')
				_w('Monitor stopped')
			except Exception as e:
				_w(f'Failed to stop monitor: {e}')
		return

	if cmd in ('quarantine', 'q'):
		def _q():
			STATE.set('deleting', 'Quarantining findings...')
			qdir = os.path.join(os.getcwd(), 'quarantine')
			os.makedirs(qdir, exist_ok=True)
			if scanner is None or not hasattr(scanner, 'QuarantineFile'):
				STATE.set('idle', 'Quarantine not available (scanner missing)')
				_w('Quarantine not available')
				return
			for f in (LAST_SCAN_RESULTS or {}).get('files', []):
				if f.get('suspicious'):
					path = f.get('path')
					try:
						scanner.QuarantineFile.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
						scanner.QuarantineFile.restype = ctypes.c_void_p
						scanner.FreeResult.argtypes = [ctypes.c_void_p]
						scanner.FreeResult.restype = None
						cptr = scanner.QuarantineFile(path.encode('utf-8'), qdir.encode('utf-8'))
						res = recv_and_free(scanner, cptr, free_name='FreeResult')
						_w(f'Quarantined: {path}')
					except Exception:
						_w(f'Failed to quarantine: {path}')
			STATE.set('idle', 'Quarantine complete')

		threading.Thread(target=_q, daemon=True).start()
		return

	if cmd == 'db':
		if not args:
			_w('Usage: db add <sha256> | db remove <sha256> | db list')
			return
		sub = args[0].lower()
		if sub == 'list':
			h = load_local_hash_db()
			_w('Local DB entries:')
			for hh in sorted(h):
				_w(' - ' + hh)
			return
		if sub == 'add' and len(args) > 1:
			hashv = args[1].strip().lower()
			if hashv.startswith('sha256:'):
				hashv = hashv.split(':', 1)[1]
			h = load_local_hash_db()
			h.add(hashv)
			if save_local_hash_db(h):
				_w('Added to DB')
			else:
				_w('Failed to save DB')
			return
		if sub == 'remove' and len(args) > 1:
			hashv = args[1].strip().lower()
			if hashv.startswith('sha256:'):
				hashv = hashv.split(':', 1)[1]
			h = load_local_hash_db()
			if hashv in h:
				h.remove(hashv)
				if save_local_hash_db(h):
					_w('Removed')
				else:
					_w('Failed to save DB')
			else:
				_w('Hash not found in DB')
			return
		_w('Unknown db command')
		return

	if cmd == 'status':
		st, msg = STATE.get()
		_w(f"State: {st} - {msg}")
		return

	if cmd == 'logs':
		for l in LOGS[-200:]:
			_w(l)
		return

	if cmd == 'save-logs' and len(args) > 0:
		path = args[0]
		try:
			with open(path, 'w', encoding='utf-8') as f:
				for l in LOGS:
					f.write(l + '\n')
			_w('Logs saved')
		except Exception as e:
			_w(f'Failed to save logs: {e}')
		return

	if cmd in ('exit', 'quit', 'x'):
		on_exit()
		return

	_w('Unknown command; type help for commands')


# --- Main ---------------------------------------------------------
def main(argv=None):
	global scanner, monitor
	# 자동으로 콘솔 없는 실행(pythonw)으로 재시작
	try:
		if os.name == 'nt' and sys.executable.lower().endswith('python.exe') and os.environ.get('MANTA_REEXECED') != '1':
			# 찾을 수 있으면 같은 폴더의 pythonw.exe를 사용
			pythonw = shutil.which('pythonw') or os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
			if pythonw and os.path.exists(pythonw):
				env = dict(os.environ)
				env['MANTA_REEXECED'] = '1'
				try:
					subprocess.Popen([pythonw, *sys.argv], env=env, close_fds=True)
					print('Re-launching without console using pythonw...')
					sys.exit(0)
				except Exception:
					# 실패하면 그냥 계속 현재 프로세스로 진행
					pass
	except Exception:
		pass
	banner_text = load_ascii_banner_text()

	# start terminal renderer
	term_stop = threading.Event()
	term_thread = threading.Thread(target=terminal_renderer, args=(banner_text, term_stop), daemon=True)
	term_thread.start()

	# optional GUI
	gui = None
	if tk is not None:
		gui = GuiWindow(banner_text)
		gui.start()
		# 트레이/윈도우 복원 제어를 위한 핸들러 저장
		try:
			# 전역으로 GUI 참조를 보관해 트레이 콜백에서 접근하게 함
			globals()['GUI_INSTANCE'] = gui
		except Exception:
			pass

	# load DLLs (best-effort)
	scanner = None
	monitor = None
	s_path = find_dist_dll("manta_scanner.dll")
	m_path = find_dist_dll("manta_monitor.dll")
	if s_path:
		try:
			scanner = load_cdll(s_path)
		except Exception:
			scanner = None
	if m_path:
		try:
			monitor = load_cdll(m_path)
		except Exception:
			monitor = None

	# simple monitor poller: if monitor exposes MonitorStart/GetEvent
	stop_mon = threading.Event()
	if monitor is not None:
		try:
			if hasattr(monitor, "MonitorStart"):
				monitor.MonitorStart()

			def poll_mon():
				while not stop_mon.is_set():
					try:
						if not hasattr(monitor, "GetEvent"):
							time.sleep(1.0)
							continue
						monitor.GetEvent.restype = ctypes.c_void_p
						ptr = monitor.GetEvent()
						if ptr:
							ev = recv_and_free(monitor, ptr, free_name="MonitorFreeResult")
							if ev and "threat" in ev.lower():
								STATE.set("threat", "Threat event from monitor")
					except Exception:
						pass
					time.sleep(0.5)

			threading.Thread(target=poll_mon, daemon=True).start()
		except Exception:
			pass

	# quarantine action (available even without tray)
	def quarantine_action():
		if LAST_SCAN_RESULTS is None:
			STATE.set("idle", "No scan results to quarantine")
			return
		STATE.set("deleting", "Quarantining findings...")
		def _q():
			qdir = os.path.join(os.getcwd(), "quarantine")
			os.makedirs(qdir, exist_ok=True)
			if scanner is None or not hasattr(scanner, "QuarantineFile"):
				STATE.set("idle", "Quarantine not available (scanner missing)")
				return
			for f in LAST_SCAN_RESULTS.get("files", []):
				if f.get("suspicious"):
					path = f.get("path")
					try:
						scanner.QuarantineFile.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
						scanner.QuarantineFile.restype = ctypes.c_void_p
						scanner.FreeResult.argtypes = [ctypes.c_void_p]
						scanner.FreeResult.restype = None
						cptr = scanner.QuarantineFile(path.encode('utf-8'), qdir.encode('utf-8'))
						res = recv_and_free(scanner, cptr, free_name="FreeResult")
					except Exception:
						pass
			STATE.set("idle", "Quarantine complete")
		threading.Thread(target=_q, daemon=True).start()

	# tray icon
	def show_gui():
		if gui and gui.root:
			try:
				gui.root.deiconify()
			except Exception:
				pass

	def start_scan():
		def _scan():
			STATE.set("scanning", "Scanning (tray)")
			if scanner is not None and hasattr(scanner, "ScanPath"):
				try:
					scanner.ScanPath.argtypes = [ctypes.c_char_p]
					scanner.ScanPath.restype = ctypes.c_void_p
					scanner.FreeResult.argtypes = [ctypes.c_void_p]
					scanner.FreeResult.restype = None
					cptr = scanner.ScanPath(b".")
					res = recv_and_free(scanner, cptr, free_name="FreeResult")
					if res:
						try:
							j = json.loads(res)
							if j.get("files"):
								STATE.set("threat", f"Found {len(j.get('files'))} items")
								return
						except Exception:
							pass
				except Exception:
					pass
			STATE.set("idle", "Scan complete")

		threading.Thread(target=_scan, daemon=True).start()

	# command processing handled by module-level process_command

	def command_input_loop():
		def log_event(msg):
			ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
			LOGS.append(f"[{ts}] {msg}")

		banner = "\nInteractive commands: scan [path], scan-async, monitor start|stop, quarantine, db add <sha256>, db remove <sha256>, db list, status, logs, save-logs <file>, help, exit\n"
		sys.stdout.write(banner)
		sys.stdout.flush()
		while True:
			try:
				# indicate we're about to read input so renderer pauses
				INPUT_ACTIVE.set()
				line = input('manta> ')
			except (EOFError, KeyboardInterrupt):
				INPUT_ACTIVE.clear()
				break
			INPUT_ACTIVE.clear()
			if not line:
				continue
			log_event(f"User requested command: {line}")
			process_command(line, writer=print)

	threading.Thread(target=command_input_loop, daemon=True).start()


	def stop_scan():
		STATE.set("idle", "Scan stopped")

	def on_exit():
		term_stop.set()
		stop_mon.set()
		if gui:
			gui.stop()
		# attempt to stop monitor DLL
		if monitor is not None and hasattr(monitor, "MonitorStop"):
			try:
				monitor.MonitorStop()
			except Exception:
				pass
		os._exit(0)

	tray = None
	if pystray is not None:
		tray = create_tray("MANTA", show_gui, start_scan, stop_scan, quarantine_action, on_exit)
		# 트레이 아이콘을 클릭하거나 더블클릭하면 창 복원
		try:
			if TRAY_ICON is not None:
				def _on_double_click(icon, item):
					try:
						g = globals().get('GUI_INSTANCE')
						if g and g.root:
							g.root.deiconify()
							GUI_VISIBLE.set()
					except Exception:
						pass
				# pystray에선 직접 콜백 연결 방식이 다르므로 단순화: 메뉴로 Show GUI 제공
				pass
		except Exception:
			pass

	try:
		while True:
			time.sleep(1.0)
	except KeyboardInterrupt:
		pass
	finally:
		term_stop.set()
		stop_mon.set()
		if gui:
			gui.stop()


if __name__ == "__main__":
	main()
	# Entry point preserved (no-op change to trigger finalization)
