"""외부 이미지 없이 배포 가능한 원본 SVG 장면 10개를 생성한다."""
from pathlib import Path
from html import escape
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'frontend/public/scenes'


def rect(x, y, w, h, fill, rx=8, **attrs):
    extra = ' '.join(f'{key.replace("_", "-")}="{value}"' for key, value in attrs.items())
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" {extra}/>'


def line(d, color='#99b4c5', width=5):
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def person(x, y, color='#edb685'):
    return f'<g transform="translate({x} {y})"><circle cy="-26" r="14" fill="{color}"/>' + line('M0 -8 V42 M0 4 L-22 24 M0 4 L22 24 M0 42 L-18 72 M0 42 L18 72', color, 10) + '</g>'


def room():
    return rect(0, 0, 720, 450, '#172b3b', 0) + rect(35, 50, 650, 290, '#243e50') + line('M0 360 H720', '#40596b', 3) + line('M35 340 L0 450 M685 340 L720 450', '#40596b', 3)


def smoke():
    return ''.join(f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{r//2}" fill="#afbac5" opacity=".14"/>' for x, y, r in [(120, 110, 110), (270, 95, 150), (470, 130, 180), (610, 90, 150)])


def elevator():
    return rect(230, 90, 260, 255, '#0c1a27') + rect(245, 105, 112, 230, '#637988', 1) + rect(362, 105, 112, 230, '#4c6273', 1) + rect(327, 61, 68, 23, '#182331', 3) + '<circle cx="362" cy="72" r="5" fill="#e6a46d"/>' + rect(510, 170, 22, 60, '#c7d2d8', 4) + '<circle cx="521" cy="193" r="4" fill="#ecaf76"/>'


def stairs():
    return line('M190 350 H260 V315 H320 V280 H380 V245 H440 V210 H500', '#b3cad4', 15) + line('M180 280 L485 105 M180 280 V335 M270 230 V290 M370 170 V232 M475 110 V180', '#7b9fae', 5)


def door():
    return rect(240, 80, 250, 280, '#111f2b') + rect(255, 95, 220, 260, '#6c4f49', 3) + rect(411, 215, 35, 8, '#dfbc97', 3) + line('M275 355 H460', '#e8a15e', 4)


def school():
    shapes = rect(35, 90, 255, 205, '#759baa') + rect(50, 72, 230, 22, '#e7b37d')
    for x in (58, 130, 202):
        for y in (116, 170, 224):
            shapes += rect(x, y, 48, 32, '#2f5264', 2)
    return shapes


def outside():
    return rect(0, 0, 720, 450, '#b5d3d9', 0) + rect(0, 295, 720, 155, '#527b6c', 0) + '<circle cx="609" cy="75" r="32" fill="#f3dab3"/>'


def desk():
    return rect(225, 240, 245, 24, '#d6a679', 3) + line('M245 265 V350 M450 265 V350', '#a5c2ca', 12) + rect(280, 200, 48, 12, '#e0c993', 2)


fire = [
    room() + rect(95, 210, 200, 130, '#6a7d85') + rect(130, 160, 118, 66, '#b0c1c4') + rect(142, 173, 70, 39, '#253d49', 2) + rect(540, 170, 35, 45, '#b75d4d') + smoke(),
    room() + elevator() + smoke() + person(568, 260),
    room() + stairs() + smoke() + person(130, 260),
    room() + door() + smoke(),
    outside() + school() + rect(403, 265, 215, 82, '#b95b49') + rect(430, 240, 88, 40, '#db8b6b') + rect(442, 248, 60, 24, '#b9d9df') + '<circle cx="445" cy="350" r="21" fill="#243b46"/><circle cx="578" cy="350" r="21" fill="#243b46"/>' + person(350, 300, '#efd3b1'),
]
quake = [
    room() + rect(90, 80, 125, 120, '#87b4c4') + line('M155 80 V200 M90 140 H215', '#d3e5e4', 5) + desk() + line('M510 130 l14 18 -15 22 16 20', '#e8b67a', 4) + person(552, 270),
    room() + desk() + rect(535, 80, 100, 260, '#5c8793') + person(530, 235) + person(590, 260, '#94bbc8'),
    room() + elevator() + line('M70 315 H110 V285 H150 V255 H190', '#bfd3dc', 8),
    outside() + school() + '<ellipse cx="510" cy="354" rx="135" ry="50" fill="none" stroke="#dde0bd" stroke-width="3"/>' + person(470, 285) + person(535, 300, '#9bc5c7'),
    outside() + rect(120, 145, 175, 120, '#284d60') + line('M140 265 V350 M275 265 V350', '#d1dad4', 9) + line('M150 180 H265 M150 203 H245 M150 227 H255', '#9cc3c8', 5) + person(440, 270) + person(510, 290, '#9bc5c7') + '<path d="M585 150 Q625 177 585 204 M606 133 Q665 177 606 221" fill="none" stroke="#466e7e" stroke-width="5"/>',
]

for sid, scenes in [('fire_office', fire), ('earthquake_school', quake)]:
    directory = OUT / sid
    directory.mkdir(parents=True, exist_ok=True)
    path = ROOT / f'data/scenarios/{sid}.json'
    scenario = json.loads(path.read_text(encoding='utf-8'))
    for stage, art in zip(scenario['stages'], scenes):
        title = escape(stage['title'])
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 450" role="img" aria-labelledby="title"><title id="title">{title} — 상황 설명용 개념도</title>{art}<rect x="24" y="20" width="155" height="25" rx="12" fill="#112b3b" opacity=".8"/><text x="38" y="38" fill="#e5d7be" font-family="sans-serif" font-size="12">SafeTurn / SCENE {stage["stage"]:02d}</text></svg>'
        (directory / f'stage{stage["stage"]}.svg').write_text(svg, encoding='utf-8')
        stage['image'] = f'{sid}/stage{stage["stage"]}.svg'
    scenario['thumbnail'] = f'{sid}/stage1.svg'
    path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Created 10 original SVG scene illustrations; scenario image paths updated.')
