"""Account-scoped reply history and an exclusive local runner lock."""
import os
import re
import sqlite3
from pathlib import Path


def post_id(url):
    match = re.search(r'/status/(\d+)(?:[/?#]|$)', url or '')
    return match.group(1) if match else None


def own_replies(data, account):
    """Read parent IDs from responses already loaded by the X browser UI."""
    nodes = []
    def visit(value):
        if isinstance(value, dict):
            nodes.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(data)
    account = account.lstrip('@').casefold()
    owners = {str(node['rest_id']) for node in nodes if node.get('rest_id') and
              ((node.get('core') or {}).get('screen_name', '').casefold() == account or
               (node.get('legacy') or {}).get('screen_name', '').casefold() == account)}
    records = {}
    for node in nodes:
        legacy = node.get('legacy') or {}
        parent = legacy.get('in_reply_to_status_id_str')
        identity = node.get('rest_id')
        if parent and identity and str(legacy.get('user_id_str')) in owners:
            records[str(parent)] = (str(parent), str(identity), legacy.get('full_text', ''))
    return list(records.values())


class ActivityStore:
    def __init__(self, path, account):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.account = account.lstrip('@').casefold()
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('''CREATE TABLE IF NOT EXISTS replies (
            account TEXT NOT NULL, post_id TEXT NOT NULL, status TEXT NOT NULL,
            reply_id TEXT, reply_text TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(account, post_id))''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS follow_backs (
            account TEXT NOT NULL, target_id TEXT NOT NULL, handle TEXT NOT NULL,
            status TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(account,target_id))''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS follow_back_state (
            account TEXT PRIMARY KEY, resume_at REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '', failures INTEGER NOT NULL DEFAULT 0,
            blocked INTEGER NOT NULL DEFAULT 0)''')
        self.db.commit()

    def contains(self, identity):
        return self.db.execute('SELECT 1 FROM replies WHERE account=? AND post_id=?',
                               (self.account, identity)).fetchone() is not None

    def knows_reply(self, identity):
        return self.db.execute('SELECT 1 FROM replies WHERE account=? AND reply_id=?',
                               (self.account, identity)).fetchone() is not None

    def reserve_send(self, identity, text):
        with self.db:
            cursor = self.db.execute('''INSERT OR IGNORE INTO replies
                (account,post_id,status,reply_text) VALUES (?,?,'sending',?)''',
                (self.account, identity, text))
        return cursor.rowcount == 1

    def mark_send_pending(self, identity):
        with self.db:
            self.db.execute('''UPDATE replies SET status='pending', updated_at=CURRENT_TIMESTAMP
                WHERE account=? AND post_id=? AND status='sending' ''', (self.account, identity))

    def remember(self, identity, reply_id, text, status='posted'):
        with self.db:
            self.db.execute('''INSERT INTO replies (account,post_id,status,reply_id,reply_text)
                VALUES (?,?,?,?,?) ON CONFLICT(account,post_id) DO UPDATE SET
                status=excluded.status,reply_id=excluded.reply_id,
                reply_text=excluded.reply_text,updated_at=CURRENT_TIMESTAMP''',
                (self.account, identity, status, reply_id, text))

    def recent_texts(self, limit=12):
        return [row[0] for row in self.db.execute('''SELECT reply_text FROM replies
            WHERE account=? AND status IN ('posted','imported') AND reply_text != ''
            ORDER BY updated_at DESC,rowid DESC LIMIT ?''', (self.account, limit))]

    def count(self):
        return self.db.execute('SELECT COUNT(*) FROM replies WHERE account=?', (self.account,)).fetchone()[0]

    def follow_status(self, identity):
        row = self.db.execute('SELECT status FROM follow_backs WHERE account=? AND target_id=?',
                              (self.account,identity)).fetchone()
        return row[0] if row else None

    def reserve_follow(self, identity, handle):
        with self.db:
            cursor = self.db.execute('''INSERT INTO follow_backs(account,target_id,handle,status)
                VALUES (?,?,?,'pending') ON CONFLICT(account,target_id) DO UPDATE SET
                status='pending',updated_at=CURRENT_TIMESTAMP WHERE follow_backs.status='limited' ''',
                (self.account,identity,handle))
        return cursor.rowcount == 1

    def mark_follow(self, identity, status):
        with self.db:
            self.db.execute('''UPDATE follow_backs SET status=?,updated_at=CURRENT_TIMESTAMP
                WHERE account=? AND target_id=?''',(status,self.account,identity))

    def follow_state(self):
        row = self.db.execute('SELECT resume_at,reason,failures,blocked FROM follow_back_state WHERE account=?',
                              (self.account,)).fetchone()
        return dict(zip(('resume_at','reason','failures','blocked'),row or (0,'',0,0)))

    def pending_follows(self, limit=5):
        return self.db.execute('''SELECT target_id,handle FROM follow_backs
            WHERE account=? AND status='pending' ORDER BY updated_at DESC LIMIT ?''',
            (self.account,limit)).fetchall()

    def set_follow_state(self, resume_at, reason='', failures=0, blocked=False):
        with self.db:
            self.db.execute('''INSERT INTO follow_back_state(account,resume_at,reason,failures,blocked)
                VALUES (?,?,?,?,?) ON CONFLICT(account) DO UPDATE SET resume_at=excluded.resume_at,
                reason=excluded.reason,failures=excluded.failures,blocked=excluded.blocked''',
                (self.account,resume_at,reason,failures,int(blocked)))

    def close(self):
        self.db.close()


class RunnerLock:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open('a+b')
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('已有持续运行实例；请先停止原实例，避免重复互动') from None

    def close(self):
        self.file.close()
