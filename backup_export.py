"""Authenticated memory-only backup, including historical and removed images."""
import io
import json
import zipfile
from pathlib import PurePosixPath
from record_management import retained_files,read_bytes


def export(vault):
    records=vault.records()
    if sum(f.get('size',0) for r in records for f in retained_files(r))>100*1024*1024:raise ValueError('100MBを超える保管庫はbackup_cloud.pyで分割せず取得してください。')
    stream=io.BytesIO();total=0
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for record in records:
            folder=PurePosixPath(record['folder'])
            if folder.is_absolute() or '..' in folder.parts:raise ValueError('バックアップのパスを確認してください。')
            folder=folder.parent/(folder.name+'_'+record['id'][:8])
            archive.writestr(str(folder/'metadata.json'),json.dumps(record,ensure_ascii=False,indent=2))
            archive.writestr(str(folder/'idea.md'),record.get('body',''))
            for file in retained_files(record):
                relative=PurePosixPath(file['path'])
                if relative.is_absolute() or '..' in relative.parts:raise ValueError('バックアップの添付パスを確認してください。')
                raw=read_bytes(vault,record,file);total+=len(raw)
                if total>100*1024*1024:raise ValueError('バックアップ合計は100MBまでです。CLIを使用してください。')
                archive.writestr(str(folder/relative),raw)
    return stream.getvalue()
