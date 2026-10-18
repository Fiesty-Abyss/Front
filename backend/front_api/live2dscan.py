"""Read-only Cubism package diagnostics. Never extracts, executes or modifies models."""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import subprocess
import threading
import zipfile
from pathlib import Path

from .filetypes.archive import zip_names
from .filetypes.live2d import moc_version

MAX_JSON = 2 * 1024 * 1024
MAX_FILES = 20000
MAX_MODELS = 100


def safe_name(name):
    name = name.replace('\\', '/')
    return bool(name and not name.startswith(('/', '-')) and ':' not in name and '..' not in name.split('/'))


def tar_read(path, entry=None, *, prefix=False):
    """Windows ships bsdtar; optional RAR support, with bounded output and timeout."""
    if os.name != 'nt':
        raise ValueError('RAR 扫描需要 Windows 自带 tar；其他平台请提供文件夹或 ZIP')
    executable = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/tar.exe'
    command = [str(executable), '-xOf' if entry else '-tf', str(path)]
    if entry:
        if not safe_name(entry):
            raise ValueError('不安全的压缩包条目')
        command += ['--', entry]
    limit = 8 if prefix else MAX_JSON
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW) as process:
        timer = threading.Timer(20, process.kill)
        timer.start()
        try:
            result = process.stdout.read(limit + (0 if prefix else 1))
            if prefix or len(result) > limit:
                process.kill()
            status = process.wait()
            if len(result) > limit:
                raise ValueError('压缩包目录或配置超出读取限额')
            if status and not prefix:
                raise ValueError('压缩包无法读取、需要密码或读取超时')
            return result
        finally:
            timer.cancel()


class Package:
    def __init__(self, path):
        self.path, self.zip = path, None
        if path.is_dir():
            names = []
            for directory, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
                for name in files:
                    fp = Path(directory) / name
                    if fp.is_symlink() or not fp.resolve().is_relative_to(path.resolve()):
                        continue
                    names.append(fp.relative_to(path).as_posix())
                    if len(names) > MAX_FILES:
                        raise ValueError('文件超过 20000，请分批扫描子目录')
            self.names = names
        elif path.suffix.lower() == '.zip':
            self.zip = zipfile.ZipFile(path)
            if len(self.zip.infolist()) > MAX_FILES:
                self.close()
                raise ValueError('包内文件超过 20000')
            self.entries = zip_names(self.zip)
            self.names = list(self.entries)
        elif path.suffix.lower() == '.rar':
            raw = tar_read(path)
            for encoding in ('utf-8', 'gb18030'):
                try:
                    self.names = raw.decode(encoding).splitlines()
                    break
                except UnicodeDecodeError:
                    pass
            else:
                raise ValueError('压缩包文件名编码无法识别')
        else:
            raise ValueError('请选择模型文件夹、ZIP 或 Windows RAR')
        if len(self.names) > MAX_FILES:
            self.close()
            raise ValueError('包内文件超过 20000')
        self.names = [n.rstrip('/') for n in self.names if safe_name(n)]
        self.lower = {n.casefold(): n for n in self.names}
        if len(self.lower) != len(self.names):
            self.close()
            raise ValueError('包内有重复或仅大小写不同的路径，无法安全确定引用')

    def read(self, name, prefix=False):
        actual = self.lower.get(name.casefold())
        if actual is None:
            raise ValueError('依赖文件不存在')
        limit = 8 if prefix else MAX_JSON
        if self.path.is_dir():
            fp = (self.path / actual).resolve()
            if not fp.is_relative_to(self.path.resolve()):
                raise ValueError('引用越过模型目录')
            with fp.open('rb') as handle:
                data = handle.read(limit + (0 if prefix else 1))
        elif self.zip:
            with self.zip.open(self.entries[actual]) as handle:
                data = handle.read(limit + (0 if prefix else 1))
        else:
            data = tar_read(self.path, actual, prefix=prefix)
        if len(data) > limit:
            raise ValueError('配置超过 2 MiB')
        return data

    def close(self):
        if self.zip:
            self.zip.close()


def diagnose(package, main, check=lambda: None):
    diagnostics, dependencies, parameters = [], [], set()
    def issue(code, file, message):
        diagnostics.append({'code': code, 'file': file, 'message': message})
    def json_file(name):
        check()
        value = json.loads(package.read(name).decode('utf-8-sig'))
        if not isinstance(value, dict):
            raise ValueError('配置必须是 JSON 对象')
        return value
    result = {'main': main, 'dependencies': dependencies, 'diagnostics': diagnostics,
              'motions': [], 'expressions': [], 'parameters': [], 'runtime_verified': False}
    root = posixpath.dirname(main)
    result['nearby_files'] = [n for n in package.names if (not root or n.startswith(root + '/')) and n.lower().endswith(('.exp3.json', '.motion3.json', '.physics3.json', '.pose3.json', '.vtube.json', '.cdi3.json'))][:500]
    def dependency(kind, value, *, required=False):
        check()
        if not isinstance(value, str) or not value:
            if required:
                issue('missing_reference', main, f'未声明 {kind}')
            return None
        target = posixpath.normpath(posixpath.join(root, value.replace('\\', '/')))
        if not safe_name(target):
            issue('unsafe_reference', value, '引用越过包根目录或使用绝对路径')
            return None
        exists = target.casefold() in package.lower
        dependencies.append({'kind': kind, 'path': target, 'exists': exists})
        if not exists:
            issue('missing_file', target, f'{kind} 文件缺失')
        elif target not in package.names:
            issue('case_mismatch', target, '文件名大小写不一致；跨平台加载可能失败')
        return target if exists else None
    try:
        desc = json_file(main)
        refs = desc.get('FileReferences')
        if not isinstance(refs, dict):
            raise ValueError('缺少 Cubism 3+ FileReferences；Cubism 2 需使用旧预览器')
        result['model_version'] = desc.get('Version')
        moc = dependency('moc', refs.get('Moc'), required=True)
        if moc:
            head = package.read(moc, prefix=True)
            version = moc_version(head)
            result['cubism'] = version
            result['moc_format_byte'] = head[4] if head[:4] == b'MOC3' and len(head) > 4 else None
            if head[:4] != b'MOC3' or len(head) < 5:
                issue('invalid_moc', moc, '无法识别 MOC3 文件头')
            elif head[4] not in range(1, 7):
                issue('unknown_moc_version', moc, '未知 MOC3 格式号；需要运行时确认版本兼容性')
        textures = refs.get('Textures')
        if not isinstance(textures, list) or not textures:
            issue('missing_textures', main, '未声明贴图')
        else:
            for texture in textures:
                dependency('texture', texture, required=True)
        for key in ('Physics', 'Pose', 'DisplayInfo', 'UserData'):
            target = dependency(key.lower(), refs.get(key))
            if target:
                try:
                    data = json_file(target)
                    if key == 'DisplayInfo':
                        parameters.update(p['Id'] for p in data.get('Parameters', []) if isinstance(p, dict) and isinstance(p.get('Id'), str))
                except (ValueError, OSError) as exc:
                    issue('invalid_config', target, str(exc))
        for expression in refs.get('Expressions') or []:
            if not isinstance(expression, dict):
                raise ValueError('表情结构不正确')
            target = dependency('expression', expression.get('File'), required=True)
            result['expressions'].append({'name': expression.get('Name') or expression.get('File'), 'file': target})
            if target:
                try:
                    data = json_file(target)
                    parameters.update(p['Id'] for p in data.get('Parameters', []) if isinstance(p, dict) and isinstance(p.get('Id'), str))
                except (ValueError, OSError) as exc:
                    issue('invalid_expression', target, str(exc))
        motions = refs.get('Motions') or {}
        if not isinstance(motions, dict):
            raise ValueError('动作分组结构不正确')
        for group, items in motions.items():
            for index, motion in enumerate(items):
                target = dependency('motion', motion.get('File'), required=True)
                dependency('sound', motion.get('Sound'))
                result['motions'].append({'group': group, 'index': index, 'file': target})
                if target:
                    try:
                        data = json_file(target)
                        parameters.update(p['Id'] for p in data.get('Curves', []) if isinstance(p, dict) and p.get('Target') == 'Parameter' and isinstance(p.get('Id'), str))
                    except (ValueError, OSError) as exc:
                        issue('invalid_motion', target, str(exc))
        for group in desc.get('Groups') or []:
            if isinstance(group, dict) and group.get('Target') == 'Parameter':
                parameters.update(p for p in group.get('Ids', []) if isinstance(p, str))
        result['parameters'] = sorted(parameters)
        result['parameter_source'] = '配置/动作/表情引用；未通过 Core 枚举全部参数或范围'
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        issue('invalid_model', main, str(exc))
    result['diagnostics'].append({'code': 'runtime_unverified', 'file': main, 'message': '尚未使用 Cubism Core 验证运行时兼容性或渲染；贴图不代表实时模型'})
    return result


def scan(path: Path, check=lambda: None):
    path = path.resolve()
    if not path.exists():
        raise ValueError('路径不存在；原模型可能已移动')
    sources = [path]
    if path.is_dir():
        # The folder itself includes all loose models; discover nested archives separately.
        sources += [p for p in path.rglob('*') if p.suffix.lower() in ('.zip', '.rar') and p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(path)]
    if len(sources) > 100:
        raise ValueError('压缩包超过 100，请分批扫描')
    results, errors = [], []
    for source in sources:
        check()
        package = None
        try:
            package = Package(source)
            for main in package.names:
                if main.lower().endswith('.model3.json'):
                    key = os.path.normcase(str((source / main).resolve())) if source.is_dir() else os.path.normcase(str(source)) + '\0' + main
                    identity = hashlib.sha256(key.encode()).hexdigest()
                    results.append({'identity': identity, 'source_path': str(source), 'title': Path(main).name.removesuffix('.model3.json'), **diagnose(package, main, check)})
                    if len(results) > MAX_MODELS:
                        raise ValueError('模型超过 100，请分批扫描')
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            errors.append({'source': str(source), 'message': str(exc)})
        finally:
            if package:
                package.close()
    return {'models': results[:MAX_MODELS], 'errors': errors}
