"""Read-only startup triage. A structure mismatch is not proof of corruption."""
from contextlib import closing
from dataclasses import dataclass,field
from pathlib import Path
import sqlite3

CODES=frozenset({'database_schema_incompatible','database_not_front','database_damaged',
    'database_locked','database_access_denied','database_unreadable','database_foreign_key_issues','database_check_failed'})


@dataclass(frozen=True)
class Diagnostic:
    code: str
    metrics: dict = field(default_factory=dict)


class StartupDatabaseError(RuntimeError):
    def __init__(self,result):
        self.diagnostic=result
        super().__init__(result.code)


def sqlite_failure(exc):
    # Extended result codes share the primary code's low byte. Never parse or
    # publish the exception text: it can contain private paths or SQL values.
    code=getattr(exc,'sqlite_errorcode',None)
    primary=(code & 255) if isinstance(code,int) else None
    # Stable SQLite primary result codes; Python 3.10 does not expose all the
    # named constants/exception attributes. Missing codes remain inconclusive.
    if primary in (11,26):return 'database_damaged'
    if primary in (5,6):return 'database_locked'
    if primary in (3,23,8):return 'database_access_denied'
    if primary in (14,10):return 'database_unreadable'
    return 'database_check_failed'


def inspect_database(path):
    from .backups import schema_findings
    # Import declarative tables, never create_app, directories, or a live engine.
    from . import models  # noqa: F401
    try:
        uri=Path(path).resolve().as_uri()+'?mode=ro'
        with closing(sqlite3.connect(uri,uri=True,timeout=1)) as db:
            db.execute('PRAGMA query_only=ON')
            integrity=db.execute('PRAGMA integrity_check').fetchall()
            if integrity!=[('ok',)]:return Diagnostic('database_damaged',{'integrity_ok':False})
            findings=schema_findings(db,complete=True)
            metrics={'integrity_ok':True,**{name:len(value) for name,value in findings.items()}}
            if findings['missing_core']:return Diagnostic('database_not_front',metrics)
            from .migrate import COLUMNS
            additive={table+'.'+column for table,column,_ in COLUMNS}
            unsupported=set(findings['missing_columns'])-additive
            metrics['unmigratable_columns']=len(unsupported)
            if findings['unknown_tables'] or findings['unknown_columns']:
                return Diagnostic('database_schema_incompatible',metrics)
            if unsupported:return Diagnostic('database_schema_incompatible',metrics)
            violations=db.execute('PRAGMA foreign_key_check').fetchmany(101)
            metrics['foreign_key_issues']=len(violations)
            metrics['foreign_key_issues_capped']=len(violations)==101
            if violations:return Diagnostic('database_foreign_key_issues',metrics)
            return Diagnostic('ok',metrics)
    except PermissionError:return Diagnostic('database_access_denied')
    except sqlite3.DatabaseError as exc:return Diagnostic(sqlite_failure(exc))
    except OSError:return Diagnostic('database_unreadable')
