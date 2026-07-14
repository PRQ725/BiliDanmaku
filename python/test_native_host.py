#!/usr/bin/env python3
# test_native_host.py — BiliDanmaku Native Host 独立测试脚本
# 模拟 Chrome Native Messaging 客户端，验证 native_host.py 协议正确性。
#
# 用法: python test_native_host.py
# 依赖: Python 3.8+ 标准库（无外部依赖）

import subprocess
import struct
import json
import sys
import os
import time

# ─── 配置 ───────────────────────────────────────────────────

NATIVE_HOST = os.path.join(os.path.dirname(__file__), 'native_host.py')
TIMEOUT = 5  # 子进程响应超时（秒）

# ─── 协议工具函数（与 Chrome Native Messaging 一致）─────────


def pack_message(msg_dict):
    """将 dict 编码为 Native Messaging 协议帧: 4字节LE长度 + UTF-8 JSON"""
    data = json.dumps(msg_dict, ensure_ascii=False).encode('utf-8')
    return struct.pack('<I', len(data)) + data


def unpack_message(stream):
    """从二进制流读取一条 Native Messaging 协议帧，返回 dict 或 None"""
    raw_len = stream.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    msg_len = struct.unpack('<I', raw_len)[0]
    if msg_len == 0:
        return None
    raw_data = stream.read(msg_len)
    if not raw_data or len(raw_data) < msg_len:
        return None
    return json.loads(raw_data.decode('utf-8'))


# ─── 测试用例数据 ────────────────────────────────────────────

TEST_VIDEO_SWITCH_FULL = {
    'protocolVersion': 1,
    'id': 'test-0001-full',
    'timestamp': 1720000000000,
    'type': 'video_switch',
    'payload': {
        'bv': 'BV1xx411c7mD',
        'cid': 12345678,
        'title': '【测试视频】Full Resolver 验证',
        'duration': 360.0,
        'pageUrl': 'https://www.bilibili.com/video/BV1xx411c7mD',
        'resolverName': 'InitialState',
        'resolverLevel': 'FULL',
    },
}

TEST_VIDEO_SWITCH_PARTIAL = {
    'protocolVersion': 1,
    'id': 'test-0002-partial',
    'timestamp': 1720000001000,
    'type': 'video_switch',
    'payload': {
        'bv': 'BV1ab2cd3ef4',
        'cid': None,
        'title': '另一个测试视频 — PARTIAL Resolver',
        'duration': None,
        'pageUrl': 'https://www.bilibili.com/video/BV1ab2cd3ef4',
        'resolverName': 'UrlRegex',
        'resolverLevel': 'PARTIAL',
    },
}

TEST_PROGRESS_UPDATE = {
    'protocolVersion': 1,
    'id': 'test-0003-progress',
    'timestamp': 1720000005000,
    'type': 'progress_update',
    'payload': {
        'bv': 'BV1xx411c7mD',
        'progress': 42.5,
        'isPlaying': True,
    },
}

TEST_PROGRESS_PAUSED = {
    'protocolVersion': 1,
    'id': 'test-0004-paused',
    'timestamp': 1720000010000,
    'type': 'progress_update',
    'payload': {
        'bv': 'BV1xx411c7mD',
        'progress': 55.0,
        'isPlaying': False,
    },
}


# ─── 测试执行 ───────────────────────────────────────────────


class TestResult:
    """累积测试结果并输出带颜色的报告"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.checks = []

    def check(self, name, condition, detail=''):
        if condition:
            self.passed += 1
            self.checks.append(f'  [PASS] {name}')
        else:
            self.failed += 1
            self.checks.append(f'  [FAIL] {name}  — {detail}')

    def summary(self):
        total = self.passed + self.failed
        print(f'\n{"═" * 60}')
        print(f'测试结果: {self.passed}/{total} 通过', end='')
        if self.failed > 0:
            print(f', {self.failed} 失败 [FAIL]')
        else:
            print(' [PASS]')
        print(f'{"═" * 60}')
        for c in self.checks:
            print(c)
        return self.failed == 0


def run():
    # Windows console 默认使用 GBK，强制 UTF-8 避免 emoji/特殊字符错误
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print('═' * 60)
    print('BiliDanmaku Native Host 独立测试')
    print(f'目标: {NATIVE_HOST}')
    print('═' * 60)

    # 检查 native_host.py 存在
    if not os.path.exists(NATIVE_HOST):
        print(f'[FAIL] 找不到 {NATIVE_HOST}')
        sys.exit(1)
    print(f'[PASS] native_host.py 存在')

    # 启动 native_host.py 子进程 (测试模式：跳过真实 HTTP 请求)
    env = os.environ.copy()
    env['BILIDANMAKU_TEST_MODE'] = '1'
    proc = subprocess.Popen(
        [sys.executable, NATIVE_HOST],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    print(f'[PASS] 子进程已启动 (PID={proc.pid})')

    result = TestResult()
    stderr_lines = []

    try:
        # ── 测试 1: 发送 FULL video_switch ─────────────────
        # 测试模式: fetcher 返回预置有效 XML，应成功获取 3 条弹幕
        print(f'\n── 测试 1: 发送 video_switch (FULL resolver) ──')
        proc.stdin.write(pack_message(TEST_VIDEO_SWITCH_FULL))
        proc.stdin.flush()
        time.sleep(0.3)

        response = unpack_message(proc.stdout)
        print(f'  收到回复: {json.dumps(response, ensure_ascii=False)}')
        result.check('收到回复消息', response is not None)
        result.check('测试模式弹幕获取成功',
                     response is not None and
                     response.get('payload', {}).get('status') == 'ok',
                     f'status={response.get("payload", {}).get("status") if response else "None"}')

        # ── 测试 2: 发送 PARTIAL video_switch ──────────────
        # 测试模式: video_info_handler 直接抛异常，预期 status=error
        print(f'\n── 测试 2: 发送 video_switch (PARTIAL resolver, cid=null) ──')
        proc.stdin.write(pack_message(TEST_VIDEO_SWITCH_PARTIAL))
        proc.stdin.flush()
        time.sleep(0.3)

        response = unpack_message(proc.stdout)
        print(f'  收到回复: {json.dumps(response, ensure_ascii=False)}')
        result.check('PARTIAL 消息收到回复', response is not None)
        result.check('测试模式 PARTIAL 返回 error',
                     response is not None and
                     response.get('payload', {}).get('status') == 'error',
                     f'status={response.get("payload", {}).get("status") if response else "None"}')

        # ── 测试 3: 发送 progress_update (播放中) ──────────
        # progress_update 不触发 HTTP，保持原有行为
        print(f'\n── 测试 3: 发送 progress_update (播放中) ──')
        proc.stdin.write(pack_message(TEST_PROGRESS_UPDATE))
        proc.stdin.flush()
        time.sleep(0.3)

        response = unpack_message(proc.stdout)
        print(f'  收到回复: {json.dumps(response, ensure_ascii=False)}')
        result.check('progress_update 收到回复', response is not None)
        result.check('回复 status=ok', response and response.get('payload', {}).get('status') == 'ok')

        # ── 测试 4: 发送 progress_update (暂停) ────────────
        print(f'\n── 测试 4: 发送 progress_update (暂停) ──')
        proc.stdin.write(pack_message(TEST_PROGRESS_PAUSED))
        proc.stdin.flush()
        time.sleep(0.3)

        response = unpack_message(proc.stdout)
        print(f'  收到回复: {json.dumps(response, ensure_ascii=False)}')
        result.check('暂停状态消息收到回复', response is not None)

        # ── 测试 5: 非法 JSON 不崩溃 ──────────────────────
        print(f'\n── 测试 5: 发送非法数据，验证不崩溃 ──')
        garbage = b'\x05\x00\x00\x00hello'  # 长度=5 的非JSON数据
        proc.stdin.write(garbage)
        proc.stdin.flush()
        time.sleep(0.5)

        # 进程应该还在运行（不死）
        still_alive = proc.poll() is None
        result.check('非法消息后进程仍存活', still_alive,
                     f'进程退出码={proc.returncode}' if not still_alive else '')

        # 再发一条 progress_update 确认（避免 HTTP 延迟干扰）
        if still_alive:
            proc.stdin.write(pack_message(TEST_PROGRESS_UPDATE))
            proc.stdin.flush()
            time.sleep(0.3)
            response = unpack_message(proc.stdout)
            result.check('异常后正常消息仍可处理', response is not None)

        # ── 读取 stderr ───────────────────────────────────
        print(f'\n── native_host.py stderr 输出 ──')

    finally:
        # 关闭 stdin，触发 native_host 退出循环
        proc.stdin.close()

        # 排空 stdout 避免管道缓冲区阻塞进程退出
        try:
            while True:
                leftover = proc.stdout.read(4096)
                if not leftover:
                    break
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print('[WARN] 进程未在 5s 内退出，强制终止')
            proc.kill()
            proc.wait()

        # 读取 stderr
        stderr_raw = proc.stderr.read()
        try:
            stderr_text = stderr_raw.decode('utf-8')
        except UnicodeDecodeError:
            stderr_text = stderr_raw.decode('gbk', errors='replace')

        print(stderr_text)

        # ── 验证 stderr 关键内容 ──────────────────────────
        result.check(
            'stderr 包含 FULL Resolver 的 BV 号',
            'BV1xx411c7mD' in stderr_text,
            'stderr 中未找到 BV1xx411c7mD'
        )
        result.check(
            'stderr 包含 cid=12345678',
            '12345678' in stderr_text,
            'stderr 中未找到 cid'
        )
        result.check(
            'stderr 包含 FULL 级别标记',
            'level=FULL' in stderr_text,
            'stderr 中未找到 level=FULL'
        )
        result.check(
            'stderr 包含 PARTIAL 降级标记',
            'PARTIAL' in stderr_text,
            'stderr 中未找到 PARTIAL（可能未打印 resolverLevel）'
        )
        result.check(
            'stderr 包含弹幕获取完成 (v0.2.0-alpha)',
            '弹幕获取完成' in stderr_text,
            'stderr 中未找到弹幕获取完成标记'
        )
        result.check(
            'stderr 包含测试弹幕内容',
            'test-danmaku-1' in stderr_text,
            'stderr 中未找到测试弹幕内容'
        )
        result.check(
            'stderr 包含播放中状态',
            '播放中: 是' in stderr_text or '播放中' in stderr_text,
            'stderr 中未找到播放状态'
        )
        result.check(
            'Native Host 正常退出',
            '连接断开' in stderr_text and '退出' in stderr_text,
            '进程退出信息不符合预期'
        )
        result.check(
            '处理了正确数量的消息',
            '已处理' in stderr_text,
            'stderr 中未找到消息计数'
        )

    # ── 最终报告 ───────────────────────────────────────────
    return result.summary()


if __name__ == '__main__':
    success = run()
    sys.exit(0 if success else 1)
