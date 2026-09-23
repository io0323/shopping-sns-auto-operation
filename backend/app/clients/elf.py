"""ELF(Enterprise LLMOps Framework)への接続。

LLM 呼び出しは ELF の Gateway を経由させ、Prompt 版・トークン・コストを横断で記録する
(ELF `docs/05_既存システム統合.md` §4)。ELF が担うのは観測・登録・制御だけで、
承認ゲート・パイプライン状態・月次予算(cost_guard)は従来どおり Harness が持つ。

- `llmops` は遅延 import する。未インストール環境(CI など)でも Harness の import は壊れない
- trace / step の記録に失敗しても、パイプライン本体は止めない(観測の失敗で本処理を落とさない)
- ELF の設定は環境変数 `ELF_CONFIG`、無ければ ELF リポジトリの config.yaml を使う
- ハンドルはスレッドごとに持つ。ELF の SQLite 接続は作ったスレッドでしか使えず、
  Harness は API(BackgroundTasks)とスケジューラが別スレッドで LLM を呼ぶため。
  進行中 trace の管理もスレッドごとになり、並行実行の trace が混ざらない
"""

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llmops.sdk import LLMOps

logger = logging.getLogger(__name__)

#: ELF 上でのシステム名(traces.system / cost_daily.system / budgets の id)
ELF_SYSTEM = "harness"

_local = threading.local()


def _current() -> "LLMOps | None":
    ops: LLMOps | None = getattr(_local, "ops", None)
    return ops


class ElfUnavailableError(RuntimeError):
    """ELF が使えないため LLM を呼べない(llmops 未インストール・設定不備)。"""


def get_llmops() -> "LLMOps | None":
    """このスレッドの ELF ハンドル。使えなければ None(理由は WARN ログ)。"""
    ops = _current()
    if ops is not None:
        return ops
    try:
        from llmops.sdk import LLMOps
    except ImportError:
        logger.warning("llmops が未インストールのため ELF を使えません")
        return None
    try:
        ops = LLMOps.load(system=ELF_SYSTEM)
    except Exception:
        logger.exception("ELF の初期化に失敗しました")
        return None
    _local.ops = ops
    return ops


def require_llmops() -> "LLMOps":
    """LLM 呼び出し用。ELF 無しで API を直接叩く経路は残さない。"""
    ops = get_llmops()
    if ops is None:
        raise ElfUnavailableError(
            "ELF(llmops)を使えないため LLM を呼べません。"
            "enterprise-llmops-framework を .venv に入れ、ELF_CONFIG を確認してください"
        )
    return ops


def reset_llmops(ops: "LLMOps | None" = None) -> None:
    """このスレッドのハンドルを差し替える(テスト用)。None で次回ロードし直す。"""
    _local.ops = ops


@contextmanager
def trace(operation: str, external_id: str | None = None, **meta: Any) -> Iterator[None]:
    """1処理(パイプライン1回など)を ELF の trace として記録する。

    ELF 側の失敗は握りつぶす。本体の例外はそのまま伝え、trace は failed で閉じる。
    """
    ctx: Any = None
    ops = get_llmops()
    if ops is not None:
        try:
            ctx = ops.trace(operation, external_id=external_id, **meta)
            ctx.__enter__()
        except Exception:
            logger.exception("ELF trace の開始に失敗しました: %s", operation)
            ctx = None
    try:
        yield
    except BaseException as exc:
        _close(ctx, type(exc), exc)
        raise
    else:
        _close(ctx, None, None)


def _close(ctx: Any, exc_type: type[BaseException] | None, exc: BaseException | None) -> None:
    if ctx is None:
        return
    try:
        ctx.__exit__(exc_type, exc, None)
    except Exception:
        logger.exception("ELF trace の終了記録に失敗しました")


@contextmanager
def step(name: str) -> Iterator[None]:
    """進行中の trace にステップの区切りを付ける。trace が無ければ何もしない。"""
    ops = _current()
    current = ops.current_trace if ops is not None else None
    if current is None:
        yield
        return
    try:
        child = current.child(name)
        child.__enter__()
    except Exception:
        logger.exception("ELF step の開始に失敗しました: %s", name)
        yield
        return
    try:
        yield
    except BaseException as exc:
        _close(child, type(exc), exc)
        raise
    else:
        _close(child, None, None)
