"""A user-supplied gateway is stored locally, never as a source-code default."""
import json
import os
from pathlib import Path
import urllib.parse


def validate_portal(url):
    if not isinstance(url, str) or not url.strip() or len(url) > 4096:
        raise ValueError('请填写校园网登录页的完整 HTTP 或 HTTPS 地址。')
    url = url.strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('登录地址必须使用 HTTP 或 HTTPS，并包含服务器名称。')
    if parsed.username is not None or parsed.password is not None:
        raise ValueError('登录地址中不能包含账号或密码。')
    try:
        expected = 443 if parsed.scheme == 'https' else 80
        if parsed.port not in (None, expected):
            raise ValueError('暂时只支持 HTTP 80 或 HTTPS 443 端口。')
    except ValueError:
        raise ValueError('暂时只支持 HTTP 80 或 HTTPS 443 端口。') from None
    if any(character.isspace() for character in parsed.netloc):
        raise ValueError('登录地址的服务器名称不能包含空格。')
    return url


def load_portal(data_folder):
    path = Path(data_folder) / 'portal.json'
    try:
        if path.stat().st_size > 16384:
            return ''
        config = json.loads(path.read_text(encoding='utf-8'))
        return validate_portal(config.get('url')) if isinstance(config, dict) else ''
    except (OSError, ValueError, TypeError):
        return ''


def save_portal(data_folder, url):
    url = validate_portal(url)
    root = Path(data_folder)
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'portal.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'url': url}, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)
    return url
