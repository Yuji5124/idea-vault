#!/usr/bin/env python3
"""Prepare a local image for an explicit ※保存 instruction; never overwrite input."""
import argparse
import io
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024


def prepare_image(source, destination):
    from PIL import Image, ImageOps
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or destination.exists() or destination.suffix.lower() != '.webp':
        raise ValueError('出力には未使用の.webpファイルを指定してください。元画像は上書きしません。')
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGBA' if ('A' in opened.getbands() or 'transparency' in opened.info) else 'RGB')
        image.thumbnail((1600, 1600))
        image.info.clear()  # Do not carry EXIF/GPS or other source metadata.
        for edge in (1600, 1280, 1024, 800):
            candidate = image.copy()
            candidate.thumbnail((edge, edge))
            for quality in (85, 75, 60):
                buffer = io.BytesIO()
                candidate.save(buffer, format='WEBP', quality=quality, method=6)
                raw = buffer.getvalue()
                if len(raw) <= MAX_BYTES:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('xb') as output:
                        output.write(raw)
                    return {'width': candidate.width, 'height': candidate.height, 'bytes': len(raw)}
    raise ValueError('画像を2MB以内に変換できませんでした。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    try:
        result = prepare_image(args.source, args.destination)
    except ImportError:
        parser.exit(1, '画像変換にはPillowが必要です。pip install Pillowで導入してください。\n')
    except Exception:
        parser.exit(1, '画像を変換できません。入力形式と未使用の.webp出力先を確認してください。\n')
    print(f"変換成功：{result['width']}×{result['height']}、{result['bytes']} bytes（2MB以内）")


if __name__ == '__main__':
    main()
