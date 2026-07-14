# test_danmaku_parser.py — danmaku_parser 单元测试
# 覆盖: 正常 XML 解析 / 空输入 / 异常输入 / 格式错误

import os
import sys
import unittest

# 确保 python/ 在 sys.path 中 (从项目根目录运行)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from danmaku_parser import DanmakuItem, DanmakuParseResult, parse_xml


class TestDanmakuParserNormal(unittest.TestCase):
    """正常 XML 解析测试"""

    @classmethod
    def setUpClass(cls):
        sample_path = os.path.join(
            os.path.dirname(__file__), 'mock', 'sample_danmaku.xml'
        )
        with open(sample_path, 'rb') as f:
            cls.sample_xml = f.read()

    def test_parse_returns_result_object(self):
        result = parse_xml(self.sample_xml)
        self.assertIsInstance(result, DanmakuParseResult)

    def test_parse_total_count(self):
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.total, 6)
        self.assertEqual(len(result.items), 6)

    def test_parse_no_skipped(self):
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.skipped, 0)

    def test_parse_source(self):
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.source, 'xml_v1')

    def test_first_danmaku_time(self):
        result = parse_xml(self.sample_xml)
        self.assertAlmostEqual(result.items[0].time, 0.5)

    def test_first_danmaku_content(self):
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.items[0].content, '前方高能预警！')

    def test_first_danmaku_mode(self):
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.items[0].mode, 1)  # 滚动

    def test_first_danmaku_color(self):
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.items[0].color, 16777215)  # 白色

    def test_first_danmaku_pool(self):
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.items[0].pool, 0)  # 普通池

    def test_top_mode_danmaku(self):
        """第3条弹幕 mode=5 (顶部)"""
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.items[2].mode, 5)

    def test_bottom_mode_danmaku(self):
        """第4条弹幕 mode=4 (底部)"""
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.items[3].mode, 4)

    def test_subtitle_pool_danmaku(self):
        """第6条弹幕 pool=1 (字幕池)"""
        result = parse_xml(self.sample_xml)
        self.assertEqual(result.items[5].pool, 1)
        self.assertEqual(result.items[5].content, '字幕测试')

    def test_all_items_have_required_fields(self):
        result = parse_xml(self.sample_xml)
        for item in result.items:
            self.assertIsInstance(item.time, float)
            self.assertIsInstance(item.content, str)
            self.assertGreater(len(item.content), 0)
            self.assertIn(item.mode, [1, 4, 5])


class TestDanmakuParserEdgeCases(unittest.TestCase):
    """边界情况测试"""

    def test_empty_bytes(self):
        result = parse_xml(b'')
        self.assertEqual(result.total, 0)
        self.assertEqual(len(result.items), 0)

    def test_whitespace_only(self):
        result = parse_xml(b'   \n  ')
        self.assertEqual(result.total, 0)

    def test_xml_with_no_d_elements(self):
        result = parse_xml(
            b'<?xml version="1.0"?><i><chatserver>chat.bilibili.com</chatserver></i>'
        )
        self.assertEqual(result.total, 0)
        self.assertEqual(result.skipped, 0)

    def test_d_with_missing_p_fields(self):
        """p 属性字段不足时应跳过该条目"""
        xml = (
            '<?xml version="1.0"?><i>'
            '<d p="0.5,1,25">few-fields</d>'
            '<d p="1.0,1,25,16777215,1700000000,0,uid123,2001">normal</d>'
            '</i>'
        )
        result = parse_xml(xml.encode('utf-8'))
        self.assertEqual(result.total, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.items[0].content, 'normal')

    def test_d_with_non_numeric_fields(self):
        """p 属性包含非数字值时跳过"""
        xml = (
            '<?xml version="1.0"?><i>'
            '<d p="abc,xyz,foo,bar,baz,qux,norf,quux">bad-numeric</d>'
            '<d p="2.0,1,25,16777215,1700000000,0,uid123,2002">normal</d>'
            '</i>'
        )
        result = parse_xml(xml.encode('utf-8'))
        self.assertEqual(result.total, 1)
        self.assertEqual(result.skipped, 1)

    def test_d_with_no_p_attribute(self):
        """缺少 p 属性时跳过"""
        result = parse_xml(
            b'<?xml version="1.0"?><i><d>no-p-attr</d></i>'
        )
        self.assertEqual(result.total, 0)
        self.assertEqual(result.skipped, 1)


class TestDanmakuParserErrors(unittest.TestCase):
    """异常输入测试 — 验证解析失败时正确抛出异常"""

    def test_malformed_xml_raises_valueerror(self):
        with self.assertRaises(ValueError) as ctx:
            parse_xml('not XML <<<>>>'.encode('utf-8'))
        self.assertIn('XML', str(ctx.exception))

    def test_empty_root_raises_valueerror(self):
        with self.assertRaises(ValueError):
            parse_xml(b'\x00\x00\x00\x00')

    def test_garbage_bytes_raises_valueerror(self):
        with self.assertRaises(ValueError):
            parse_xml(b'\xff\xfe\xfd\xfc' * 10)


class TestDanmakuItemDataclass(unittest.TestCase):
    """DanmakuItem 数据类基本验证"""

    def test_create_item(self):
        item = DanmakuItem(
            time=1.5,
            content='测试弹幕',
            mode=1,
            font_size=25,
            color=16777215,
            timestamp=1700000000,
            danmaku_id=100,
            pool=0,
        )
        self.assertEqual(item.time, 1.5)
        self.assertEqual(item.content, '测试弹幕')


if __name__ == '__main__':
    # Windows console UTF-8
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    unittest.main(verbosity=2)
