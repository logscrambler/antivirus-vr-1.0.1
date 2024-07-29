# -*- coding:utf-8 -*-



import re
import sys
import os
import struct
import marshal
import zlib

s = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
) + os.sep + 'Engine' + os.sep + 'kavcore'

sys.path.append(s)

import k2timelib


# -------------------------------------------------------------------------
# 한 파일에 생성할 악성코드 패턴 최대 개수
# -------------------------------------------------------------------------
MAX_COUNT = 100000

# -------------------------------------------------------------------------
# virus.db 파일에서 사용할 주석문 정규표현식
# -------------------------------------------------------------------------
re_comment = r'#.*'

# -------------------------------------------------------------------------
# 자료 구조
# -------------------------------------------------------------------------
size_sig = {}  # 크기와 ID 저장
p1_sig = []  # CS1
p2_sig = []  # CS2
name_sig = []  # 악성코드 이름


def printProgress(_off, _all):
    if _off != 0:
        percent = (_off * 100.) / _all

        s_num = int(percent / 5)
        space_num = 20 - s_num

        sys.stdout.write('[*] Download : [')
        sys.stdout.write('#' * s_num)
        sys.stdout.write(' ' * space_num)
        sys.stdout.write('] ')
        sys.stdout.write('%3d%%  (%d/%d)\r' % (int(percent), _off, _all))


# -------------------------------------------------------------------------
# 텍스트 라인을 분석해서 악성코드 패턴을 위한 자료구조를 만든다.
# -------------------------------------------------------------------------
def add_signature(line):
    t = line.split(':')

    size = int(t[0], 16)  # flag를 기존 mdb의 크기처럼 처리 단, 16진수로 처리됨

    cs1 = t[1].split(',')  # CS1
    cs1_flag = int(cs1[0].strip(), 16)
    cs1_off = int(cs1[1].strip(), 16)
    cs1_size = int(cs1[2].strip(), 16)
    cs1_crc32 = int(cs1[3].strip(), 16)

    cs2 = t[2].split(',')  # CS2
    cs2_flag = int(cs2[0].strip(), 16)
    cs2_off = int(cs2[1].strip(), 16)
    cs2_size = int(cs2[2].strip(), 16)
    cs2_crc32 = int(cs2[3].strip(), 16)

    name = t[3]

    # 크기 추가
    sig_id = size_sig.get(size, [])
    sig_id.append(len(p1_sig))
    size_sig[size] = sig_id

    p1_sig.append([cs1_flag, cs1_off, cs1_size, cs1_crc32])

    if name in name_sig:  # 이미 등록된 이름이면 id만 획득
        name_id = name_sig.index(name)
    else:
        name_id = len(name_sig)
        name_sig.append(name)

    p2_sig.append([cs2_flag, cs2_off, cs2_size, cs2_crc32, name_id])


# -------------------------------------------------------------------------
# 자료구조에 담긴 정보를 악성코드 패턴 파일로 저장한다.
# -------------------------------------------------------------------------
def save_signature(fname, _id):
    # 현재 날짜와 시간을 구한다.
    ret_date = k2timelib.get_now_date()
    ret_time = k2timelib.get_now_time()

    # 날짜와 시간 값을 2Byte로 변경한다.
    val_date = struct.pack('<H', ret_date)
    val_time = struct.pack('<H', ret_time)

    # 크기 파일 저장 : ex) script.s01
    sname = '%s.s%02d' % (fname, _id)
    t = zlib.compress(marshal.dumps(size_sig))
    t = 'KAVS' + struct.pack('<L', len(size_sig)) + val_date + val_time + t
    save_file(sname, t)

    # 패턴 p1 파일 저장 : ex) script.i01
    sname = '%s.i%02d' % (fname, _id)
    t = zlib.compress(marshal.dumps(p1_sig))
    t = 'KAVS' + struct.pack('<L', len(p1_sig)) + val_date + val_time + t
    save_file(sname, t)

    # 패턴 p2 파일 저장 : ex) script.c01
    sname = '%s.c%02d' % (fname, _id)
    t = zlib.compress(marshal.dumps(p2_sig))
    t = 'KAVS' + struct.pack('<L', len(p2_sig)) + val_date + val_time + t
    save_file(sname, t)

    # 악성코드 이름 파일 저장 : ex) script.n01
    sname = '%s.n%02d' % (fname, _id)
    t = zlib.compress(marshal.dumps(name_sig))
    t = 'KAVS' + struct.pack('<L', len(name_sig)) + val_date + val_time + t
    save_file(sname, t)


# -------------------------------------------------------------------------
# 파일을 생성한다.
# -------------------------------------------------------------------------
def save_file(fname, data):
    fp = open(fname, 'wb')
    fp.write(data)
    fp.close()


# -------------------------------------------------------------------------
# ID별로 파일을 생성한다.
# -------------------------------------------------------------------------
def save_sig_file(fname, _id):
    # 주어진 패턴 파일명을 이용해서 sig 파일을 만듦
    t = os.path.abspath(fname)
    _, t = os.path.split(t)
    name = os.path.splitext(t)[0]
    save_signature(name, _id)

    # 초기화
    global size_sig
    global p1_sig
    global p2_sig
    global name_sig

    size_sig = []  # 크기와 ID 저장
    p1_sig = {}  # MD5 앞쪽 6Byte
    p2_sig = []  # MD5 앞쪽 10Byte
    name_sig = []  # 악성코드 이름


# -------------------------------------------------------------------------
# 텍스트 형태의 악성코드 패턴 DB 파일을 분석해서 악성코드 패턴 파일들을 생성한다.
# -------------------------------------------------------------------------
def make_signature(fname, _id):
    fp = open(fname, 'rb')

    idx = 0

    while True:
        line = fp.readline()
        if not line:
            break

        # 주석문 및 화이트 스페이스 제거
        line = re.sub(re_comment, '', line)
        line = line.strip()  # re.sub(r'\s', '', line)

        if len(line) == 0:
            continue  # 아무것도 없다면 다음줄로...

        add_signature(line)

        idx += 1
        printProgress(idx, MAX_COUNT)

        if idx >= MAX_COUNT:
            print ('[*] %s : %d' % (fname, _id))
            save_sig_file(fname, _id)
            idx = 0
            _id += 1

    fp.close()

    save_sig_file(fname, _id)


# -------------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------------
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print ('Usage : sigtool_vdb.py [sig text] [id]')
        exit(0)

    if len(sys.argv) == 2:
        sin_fname = sys.argv[1]
        _id = 1
    elif len(sys.argv) == 3:
        sin_fname = sys.argv[1]
        _id = int(sys.argv[2])

    make_signature(sin_fname, _id)
