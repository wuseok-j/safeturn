"""HWP 5의 주간보고서 블록을 복제하고 원본의 다른 양식은 보존한다.

압축 후 기존 OLE 스트림 용량 안에 들어가는 경우에만 새 복사본에 쓴다.
원본에는 쓰지 않으며 네이티브 앱 시각 검증을 대체하지 않는다.
"""
import hashlib
import shutil
import struct
import sys
import zlib
from pathlib import Path
import olefile


def records(data):
    pos = 0
    while pos < len(data):
        start = pos
        header = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        size = header >> 20
        if size == 4095:
            size = struct.unpack_from('<I', data, pos)[0]
            pos += 4
        end = pos + size
        if end > len(data):
            raise ValueError('잘못된 HWP 레코드 길이')
        yield start, header & 1023, (header >> 10) & 1023, data[pos:end]
        pos = end


def para_text(data):
    words = struct.unpack('<' + 'H' * (len(data) // 2), data)
    result, index = [], 0
    while index < len(words):
        value = words[index]
        if value in (1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23):
            index += 8
            continue
        if value >= 32:
            result.append(chr(value))
        index += 1
    return ''.join(result)


def main(source, target):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError('원본 덮어쓰기 금지')
    original_hash = hashlib.sha256(source.read_bytes()).digest()
    with olefile.OleFileIO(str(source)) as ole:
        header = ole.openstream('FileHeader').read()
        if not struct.unpack_from('<I', header, 36)[0] & 1:
            raise ValueError('압축 HWP5만 지원')
        packed = ole.openstream('BodyText/Section0').read()
        raw = zlib.decompress(packed, -15)
        preview_size = len(ole.openstream('PrvText').read())
    blocks = []
    for offset, tag, level, data in records(raw):
        if level == 0:
            blocks.append({'offset': offset, 'texts': []})
        if tag == 67:
            blocks[-1]['texts'].append(para_text(data))
    weekly = next(i for i, block in enumerate(blocks) if any('현장실습 주간보고서' in text for text in block['texts']))
    results = next(i for i, block in enumerate(blocks) if any('현장실습 결과보고서' in text for text in block['texts']))
    if '별첨1' not in ''.join(blocks[weekly - 1]['texts']).replace(' ', ''):
        raise ValueError('주간보고서 경계 확인 실패')
    if '별첨2' not in ''.join(blocks[results - 1]['texts']).replace(' ', ''):
        raise ValueError('결과보고서 경계 확인 실패')
    start, end = blocks[weekly - 1]['offset'], blocks[results - 1]['offset']
    block = raw[start:end]
    # 복제되는 블록의 첫 문단이 쪽 나누기를 포함해야 한다.
    first = next(records(block))
    if first[1] != 66 or not first[3][11] & 4:
        raise ValueError('쪽 나누기 확인 실패')
    expanded = raw[:start] + block * 4 + raw[end:]
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    new_packed = compressor.compress(expanded) + compressor.flush()
    if len(new_packed) > len(packed):
        raise ValueError('기존 OLE 스트림 용량 초과: 파일 생성 중단')
    texts = [para_text(data) for _, tag, _, data in records(expanded) if tag == 67]
    all_text = '\r\n'.join(texts)
    for title, count in [('현장실습 주간보고서', 4), ('현장실습 결과보고서', 1), ('현장실습 결석사유서', 1)]:
        if all_text.count(title) != count:
            raise ValueError(f'{title} 복제 수 검증 실패')
    # 프리뷰도 새 본문 기준으로 갱신하되 원래 스트림 크기는 유지한다.
    preview = all_text.encode('utf-16le', errors='replace')[:preview_size]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    with olefile.OleFileIO(str(target), write_mode=True) as ole:
        ole.write_stream('BodyText/Section0', new_packed.ljust(len(packed), b'\0'))
        ole.write_stream('PrvText', preview.ljust(preview_size, b'\0'))
    with olefile.OleFileIO(str(target)) as ole:
        check = zlib.decompress(ole.openstream('BodyText/Section0').read(), -15)
        assert check == expanded
        assert check[:start] == raw[:start]
        assert check[start + len(block) * 4:] == raw[end:]
        assert len(list(records(check))) > len(list(records(raw)))
    assert hashlib.sha256(source.read_bytes()).digest() == original_hash
    print('PASS: weekly form x4; other forms and source preserved; HWP records validate')
    print(target)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
