# test_dispatcher.py — events.py + data_dispatcher.py 单元测试
# 覆盖: 事件数据类 / 订阅 / 发布 / 取消订阅 / 线程安全 / 异常隔离
#
# 用法: python -m pytest tests/test_dispatcher.py -v
#       或在项目根目录: python tests/test_dispatcher.py

import os
import sys
import threading
import time
import unittest

# 确保 python/ 在 sys.path 中 (从项目根目录运行)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from events import (
    DanmakuLoadedEvent,
    EventType,
    ProgressUpdatedEvent,
    VideoSwitchedEvent,
    VideoUnloadEvent,
)
from data_dispatcher import DataDispatcher, dispatcher


# ═══════════════════════════════════════════════════════════════
# events.py 测试
# ═══════════════════════════════════════════════════════════════


class TestEventTypeEnum(unittest.TestCase):
    """EventType 枚举定义测试"""

    def test_four_event_types_defined(self):
        self.assertEqual(len(EventType), 4)

    def test_video_switched_exists(self):
        self.assertIsInstance(EventType.VIDEO_SWITCHED, EventType)

    def test_danmaku_loaded_exists(self):
        self.assertIsInstance(EventType.DANMAKU_LOADED, EventType)

    def test_progress_updated_exists(self):
        self.assertIsInstance(EventType.PROGRESS_UPDATED, EventType)

    def test_video_unload_exists(self):
        self.assertIsInstance(EventType.VIDEO_UNLOAD, EventType)

    def test_auto_values_are_unique(self):
        values = [e.value for e in EventType]
        self.assertEqual(len(values), len(set(values)))


class TestVideoSwitchedEvent(unittest.TestCase):
    """VideoSwitchedEvent 数据类测试"""

    def test_basic_construction(self):
        evt = VideoSwitchedEvent(bv='BV1xx411c7mD')
        self.assertEqual(evt.bv, 'BV1xx411c7mD')
        self.assertIsNone(evt.cid)
        self.assertEqual(evt.title, '')
        self.assertIsNone(evt.duration)
        self.assertEqual(evt.resolver_level, 'UNKNOWN')
        self.assertIsNone(evt.cookie)

    def test_full_construction(self):
        evt = VideoSwitchedEvent(
            bv='BV1xx411c7mD',
            cid=12345678,
            title='测试视频',
            duration=360.0,
            resolver_level='FULL',
            cookie='buvid3=test123; buvid4=test456',
        )
        self.assertEqual(evt.bv, 'BV1xx411c7mD')
        self.assertEqual(evt.cid, 12345678)
        self.assertEqual(evt.title, '测试视频')
        self.assertEqual(evt.duration, 360.0)
        self.assertEqual(evt.resolver_level, 'FULL')
        self.assertEqual(evt.cookie, 'buvid3=test123; buvid4=test456')

    def test_partial_resolver_defaults(self):
        """PARTIAL resolver 场景: cid=None, duration=None"""
        evt = VideoSwitchedEvent(
            bv='BV1ab2cd3ef4',
            resolver_level='PARTIAL',
        )
        self.assertIsNone(evt.cid)
        self.assertIsNone(evt.duration)

    def test_no_cookie_for_fresh_session(self):
        evt = VideoSwitchedEvent(bv='BVtest')
        self.assertIsNone(evt.cookie)


class TestDanmakuLoadedEvent(unittest.TestCase):
    """DanmakuLoadedEvent 数据类测试"""

    def test_success_construction_with_items(self):
        items = [
            {'time': 1.5, 'content': '弹幕1'},
            {'time': 2.0, 'content': '弹幕2'},
        ]
        evt = DanmakuLoadedEvent(
            bv='BV1xx411c7mD',
            cid=12345678,
            title='测试视频',
            success=True,
            items=items,
            total=2,
            summary='获取完成: 2 条',
        )
        self.assertTrue(evt.success)
        self.assertEqual(evt.bv, 'BV1xx411c7mD')
        self.assertEqual(evt.cid, 12345678)
        self.assertEqual(evt.total, 2)
        self.assertEqual(len(evt.items), 2)
        self.assertIsNone(evt.error)
        self.assertEqual(evt.summary, '获取完成: 2 条')

    def test_failure_construction_with_error(self):
        evt = DanmakuLoadedEvent(
            bv='BV1xx411c7mD',
            cid=0,
            title='',
            success=False,
            error='cid 补全失败: HTTP 500',
            summary='[错误] cid 补全失败',
        )
        self.assertFalse(evt.success)
        self.assertEqual(evt.error, 'cid 补全失败: HTTP 500')
        self.assertEqual(evt.items, [])
        self.assertEqual(evt.total, 0)

    def test_empty_danmaku_list_defaults(self):
        evt = DanmakuLoadedEvent(bv='BVtest', cid=1)
        self.assertEqual(evt.items, [])
        self.assertEqual(evt.total, 0)
        self.assertFalse(evt.success)

    def test_preserves_item_order(self):
        """items 列表顺序应与传入时一致"""
        items = [{'time': 3.0}, {'time': 1.0}, {'time': 2.0}]
        evt = DanmakuLoadedEvent(bv='BVtest', cid=1, items=items, success=True)
        self.assertEqual([i['time'] for i in evt.items], [3.0, 1.0, 2.0])


class TestProgressUpdatedEvent(unittest.TestCase):
    """ProgressUpdatedEvent 数据类测试"""

    def test_basic_construction(self):
        evt = ProgressUpdatedEvent(
            bv='BV1xx411c7mD',
            progress=42.5,
            is_playing=True,
        )
        self.assertEqual(evt.bv, 'BV1xx411c7mD')
        self.assertEqual(evt.progress, 42.5)
        self.assertTrue(evt.is_playing)

    def test_paused_state(self):
        evt = ProgressUpdatedEvent(
            bv='BV1xx411c7mD',
            progress=55.0,
            is_playing=False,
        )
        self.assertFalse(evt.is_playing)

    def test_zero_progress(self):
        evt = ProgressUpdatedEvent(bv='BVtest', progress=0.0)
        self.assertEqual(evt.progress, 0.0)
        self.assertFalse(evt.is_playing)


# ═══════════════════════════════════════════════════════════════
# data_dispatcher.py 测试
# ═══════════════════════════════════════════════════════════════


class TestDataDispatcherSubscribe(unittest.TestCase):
    """订阅功能测试"""

    def setUp(self):
        self.d = DataDispatcher()

    def test_subscribe_valid_event_type(self):
        received = []
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: received.append(e))
        self.assertEqual(self.d.subscriber_count(EventType.DANMAKU_LOADED), 1)

    def test_subscribe_multiple_same_type(self):
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.assertEqual(self.d.subscriber_count(EventType.DANMAKU_LOADED), 2)

    def test_subscribe_different_types(self):
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.d.subscribe(EventType.PROGRESS_UPDATED, lambda e: None)
        self.d.subscribe(EventType.VIDEO_SWITCHED, lambda e: None)
        self.assertEqual(self.d.subscriber_count(), 3)

    def test_subscribe_invalid_event_type_raises_typeerror(self):
        with self.assertRaises(TypeError):
            self.d.subscribe('not_an_enum', lambda e: None)

    def test_subscribe_non_enum_raises_typeerror(self):
        with self.assertRaises(TypeError):
            self.d.subscribe(123, lambda e: None)


class TestDataDispatcherPublish(unittest.TestCase):
    """发布功能测试"""

    def setUp(self):
        self.d = DataDispatcher()

    def test_publish_delivers_to_subscriber(self):
        received = []
        self.d.subscribe(
            EventType.DANMAKU_LOADED,
            lambda e: received.append(e),
        )
        evt = DanmakuLoadedEvent(bv='BVtest', cid=1, total=42)
        self.d.publish(evt)
        self.assertEqual(len(received), 1)
        self.assertIs(received[0], evt)

    def test_publish_delivers_to_all_subscribers(self):
        received = []
        for _ in range(3):
            self.d.subscribe(
                EventType.DANMAKU_LOADED,
                lambda e, r=received: r.append(e),
            )
        evt = DanmakuLoadedEvent(bv='BVtest', cid=1)
        self.d.publish(evt)
        self.assertEqual(len(received), 3)

    def test_publish_only_notifies_matching_type(self):
        """发布 DANMAKU_LOADED 不应触发 PROGRESS_UPDATED 的订阅者"""
        danmaku_received = []
        progress_received = []
        self.d.subscribe(
            EventType.DANMAKU_LOADED,
            lambda e: danmaku_received.append(e),
        )
        self.d.subscribe(
            EventType.PROGRESS_UPDATED,
            lambda e: progress_received.append(e),
        )

        self.d.publish(DanmakuLoadedEvent(bv='BVtest', cid=1))
        self.assertEqual(len(danmaku_received), 1)
        self.assertEqual(len(progress_received), 0)

    def test_publish_to_no_subscribers_does_not_crash(self):
        """没有订阅者时发布不应崩溃"""
        evt = DanmakuLoadedEvent(bv='BVtest', cid=1)
        try:
            self.d.publish(evt)
        except Exception as e:
            self.fail(f'发布到无订阅者的类型时崩溃: {e}')

    def test_publish_invalid_event_type_raises(self):
        """发布没有 EventType 映射的类应抛出 TypeError"""
        class UnknownEvent:
            pass
        with self.assertRaises(TypeError):
            self.d.publish(UnknownEvent())

    def test_publish_non_event_class_raises(self):
        """类名不以 Event 结尾"""
        with self.assertRaises(TypeError):
            self.d.publish(object())

    def test_subscriber_receives_event_with_correct_data(self):
        received = []
        self.d.subscribe(
            EventType.PROGRESS_UPDATED,
            lambda e: received.append((e.bv, e.progress, e.is_playing)),
        )
        self.d.publish(ProgressUpdatedEvent(
            bv='BVtest', progress=123.45, is_playing=True,
        ))
        self.assertEqual(received, [('BVtest', 123.45, True)])


class TestDataDispatcherUnsubscribe(unittest.TestCase):
    """取消订阅功能测试"""

    def setUp(self):
        self.d = DataDispatcher()

    def test_unsubscribe_existing_callback(self):
        cb = lambda e: None
        self.d.subscribe(EventType.DANMAKU_LOADED, cb)
        self.assertTrue(self.d.unsubscribe(EventType.DANMAKU_LOADED, cb))
        self.assertEqual(self.d.subscriber_count(EventType.DANMAKU_LOADED), 0)

    def test_unsubscribe_nonexistent_callback(self):
        cb = lambda e: None
        self.assertFalse(self.d.unsubscribe(EventType.DANMAKU_LOADED, cb))

    def test_unsubscribe_wrong_event_type(self):
        cb = lambda e: None
        self.d.subscribe(EventType.DANMAKU_LOADED, cb)
        self.assertFalse(self.d.unsubscribe(EventType.PROGRESS_UPDATED, cb))
        self.assertEqual(self.d.subscriber_count(EventType.DANMAKU_LOADED), 1)

    def test_unsubscribe_only_removes_one(self):
        """取消一个订阅者不影响同类型的其他订阅者"""
        received = []
        cb1 = lambda e: received.append('cb1')
        cb2 = lambda e: received.append('cb2')
        self.d.subscribe(EventType.DANMAKU_LOADED, cb1)
        self.d.subscribe(EventType.DANMAKU_LOADED, cb2)

        self.d.unsubscribe(EventType.DANMAKU_LOADED, cb1)
        self.d.publish(DanmakuLoadedEvent(bv='BVtest', cid=1))

        self.assertEqual(received, ['cb2'])


class TestDataDispatcherSubscriberCount(unittest.TestCase):
    """subscriber_count 查询测试"""

    def setUp(self):
        self.d = DataDispatcher()

    def test_empty_dispatcher_returns_zero(self):
        self.assertEqual(self.d.subscriber_count(), 0)
        self.assertEqual(self.d.subscriber_count(EventType.DANMAKU_LOADED), 0)

    def test_per_type_count(self):
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.d.subscribe(EventType.PROGRESS_UPDATED, lambda e: None)

        self.assertEqual(self.d.subscriber_count(EventType.DANMAKU_LOADED), 2)
        self.assertEqual(self.d.subscriber_count(EventType.PROGRESS_UPDATED), 1)
        self.assertEqual(self.d.subscriber_count(EventType.VIDEO_SWITCHED), 0)

    def test_total_count(self):
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.d.subscribe(EventType.PROGRESS_UPDATED, lambda e: None)

        self.assertEqual(self.d.subscriber_count(), 3)

    def test_count_after_unsubscribe(self):
        cb = lambda e: None
        self.d.subscribe(EventType.DANMAKU_LOADED, cb)
        self.d.unsubscribe(EventType.DANMAKU_LOADED, cb)
        self.assertEqual(self.d.subscriber_count(), 0)


class TestDataDispatcherReset(unittest.TestCase):
    """reset 功能测试"""

    def setUp(self):
        self.d = DataDispatcher()

    def test_reset_clears_all_subscribers(self):
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.d.subscribe(EventType.PROGRESS_UPDATED, lambda e: None)
        self.d.reset()
        self.assertEqual(self.d.subscriber_count(), 0)

    def test_reset_then_resubscribe_works(self):
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: None)
        self.d.reset()
        received = []
        self.d.subscribe(EventType.DANMAKU_LOADED, lambda e: received.append(e))
        evt = DanmakuLoadedEvent(bv='BVtest', cid=1)
        self.d.publish(evt)
        self.assertEqual(len(received), 1)


class TestDataDispatcherExceptionIsolation(unittest.TestCase):
    """异常隔离测试 — 一个订阅者崩溃不影响其他订阅者"""

    def setUp(self):
        self.d = DataDispatcher()

    def test_exception_in_one_subscriber_does_not_block_others(self):
        received = []
        def crashing_subscriber(event):
            raise RuntimeError('模拟崩溃')
        def normal_subscriber(event):
            received.append(event)

        self.d.subscribe(EventType.DANMAKU_LOADED, crashing_subscriber)
        self.d.subscribe(EventType.DANMAKU_LOADED, normal_subscriber)

        evt = DanmakuLoadedEvent(bv='BVtest', cid=1, total=99)
        # 不应抛出异常
        try:
            self.d.publish(evt)
        except RuntimeError:
            self.fail('发布时因订阅者异常而崩溃')

        self.assertEqual(len(received), 1)
        self.assertIs(received[0], evt)

    def test_all_subscribers_crash_still_does_not_propagate(self):
        def crashing(_):
            raise RuntimeError('崩溃')
        self.d.subscribe(EventType.DANMAKU_LOADED, crashing)
        self.d.subscribe(EventType.DANMAKU_LOADED, crashing)

        try:
            self.d.publish(DanmakuLoadedEvent(bv='BVtest', cid=1))
        except RuntimeError:
            self.fail('发布时因订阅者异常而崩溃')


class TestDataDispatcherThreadSafety(unittest.TestCase):
    """线程安全测试"""

    def setUp(self):
        self.d = DataDispatcher()

    def test_concurrent_publish_from_multiple_threads(self):
        """多线程同时发布不应丢消息或崩溃"""
        received = []
        self.d.subscribe(
            EventType.PROGRESS_UPDATED,
            lambda e: received.append(e.bv),
        )

        def publish_bv(bv_suffix):
            for _ in range(50):
                self.d.publish(ProgressUpdatedEvent(
                    bv=f'BV{bv_suffix}', progress=0.0,
                ))

        threads = []
        for i in range(4):
            t = threading.Thread(target=publish_bv, args=(f't{i}',))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(received), 200)

    def test_concurrent_subscribe_and_publish(self):
        """并发订阅和发布不应破坏注册表"""
        errors = []

        def subscriber(event):
            pass

        def do_publish():
            try:
                for _ in range(100):
                    self.d.publish(DanmakuLoadedEvent(bv='BVtest', cid=1))
            except Exception as e:
                errors.append(e)

        def do_subscribe():
            try:
                for _ in range(100):
                    cb = lambda e: None
                    self.d.subscribe(EventType.DANMAKU_LOADED, cb)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(4):
            threads.append(threading.Thread(target=do_publish))
            threads.append(threading.Thread(target=do_subscribe))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])

    def test_concurrent_subscribe_unsubscribe_publish(self):
        """并发 订阅/取消/发布 不应异常"""
        errors = []

        def worker():
            try:
                for i in range(50):
                    cb = lambda e, n=i: None
                    self.d.subscribe(EventType.DANMAKU_LOADED, cb)
                    self.d.publish(DanmakuLoadedEvent(bv=f'BV{i:03d}', cid=1))
                    self.d.unsubscribe(EventType.DANMAKU_LOADED, cb)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class TestDataDispatcherEventTypeInference(unittest.TestCase):
    """_event_type 推断逻辑测试"""

    def setUp(self):
        self.d = DataDispatcher()

    def test_danmaku_loaded_maps_correctly(self):
        evt = DanmakuLoadedEvent(bv='BVtest', cid=1)
        self.assertEqual(
            self.d._event_type(evt),
            EventType.DANMAKU_LOADED,
        )

    def test_video_switched_maps_correctly(self):
        evt = VideoSwitchedEvent(bv='BVtest')
        self.assertEqual(
            self.d._event_type(evt),
            EventType.VIDEO_SWITCHED,
        )

    def test_progress_updated_maps_correctly(self):
        evt = ProgressUpdatedEvent(bv='BVtest', progress=0.0)
        self.assertEqual(
            self.d._event_type(evt),
            EventType.PROGRESS_UPDATED,
        )

    def test_video_unload_maps_correctly(self):
        evt = VideoUnloadEvent()
        self.assertEqual(
            self.d._event_type(evt),
            EventType.VIDEO_UNLOAD,
        )

    def test_class_name_without_event_suffix_raises(self):
        class BadEvent:
            pass
        with self.assertRaises(TypeError) as ctx:
            self.d._event_type(BadEvent())
        self.assertIn('Event', str(ctx.exception))

    def test_unknown_event_name_raises(self):
        """类名以 Event 结尾但映射不到任何 EventType"""
        class FooBarEvent:
            pass
        with self.assertRaises(TypeError) as ctx:
            self.d._event_type(FooBarEvent())
        self.assertIn('FOO_BAR', str(ctx.exception))


class TestModuleLevelSingleton(unittest.TestCase):
    """模块级 dispatcher 单例测试"""

    def test_dispatcher_is_data_dispatcher_instance(self):
        self.assertIsInstance(dispatcher, DataDispatcher)

    def test_singleton_is_usable(self):
        received = []
        dispatcher.subscribe(
            EventType.DANMAKU_LOADED,
            lambda e: received.append(e),
        )
        evt = DanmakuLoadedEvent(bv='BVsingleton', cid=42)
        dispatcher.publish(evt)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].bv, 'BVsingleton')

        # 清理 — 避免影响其他测试
        dispatcher.reset()


# ═══════════════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    unittest.main(verbosity=2)
