import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from photointegral.cli import main
from photointegral.config import parse_strategy_arg, strategies_from_config
from photointegral.models import Photo
from photointegral.plan import Plan
from photointegral.rules import RulesStrategy, render_album
from photointegral.sinks import FolderSink
from photointegral.sources import FolderSource
from photointegral.strategies import PRESETS, build

from tests.helpers import make_jpeg, make_png


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lib = self.tmp / "DCIM"
        t = datetime(2024, 5, 1, 10, 0)
        make_jpeg(self.lib / "IMG_0001.JPG", t, gps=(35.0116, 135.7681))
        make_jpeg(self.lib / "IMG_0002.JPG", t + timedelta(seconds=5), gps=(35.0116, 135.7681), pattern=1)
        shutil.copy(self.lib / "IMG_0001.JPG", self.lib / "IMG_0001 copy.JPG")
        make_jpeg(self.lib / "IMG_0003.JPG", datetime(2023, 12, 24, 20, 0), color=(20, 120, 220),
                  lens="iPhone 15 Pro front camera 2.69mm f/1.9")
        make_png(self.lib / "IMG_0004.PNG")
        (self.lib / "IMG_0005.MOV").write_bytes(b"\x00" * 100)
        make_jpeg(self.lib / "IMG_0005.JPG", datetime(2022, 7, 1, 9, 0), color=(0, 200, 0))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def photos(self):
        return {p.filename: p for p in FolderSource(self.lib).photos()}


class TestFolderSource(LibraryTestCase):
    def test_exif_fields(self):
        p = self.photos()
        self.assertEqual(p["IMG_0001.JPG"].date, datetime(2024, 5, 1, 10, 0))
        self.assertEqual(p["IMG_0001.JPG"].camera_model, "iPhone 15 Pro")
        self.assertAlmostEqual(p["IMG_0001.JPG"].latitude, 35.0116, places=3)
        self.assertAlmostEqual(p["IMG_0001.JPG"].longitude, 135.7681, places=3)
        self.assertTrue(p["IMG_0003.JPG"].is_selfie)
        self.assertTrue(p["IMG_0004.PNG"].is_screenshot)
        self.assertTrue(p["IMG_0005.MOV"].is_video)
        self.assertTrue(p["IMG_0005.MOV"].is_live and p["IMG_0005.JPG"].is_live)
        self.assertFalse(p["IMG_0001.JPG"].is_live)


class TestStrategies(LibraryTestCase):
    def run_strategy(self, spec):
        return build(spec).run(list(self.photos().values()))

    def names(self, photos):
        return sorted(p.filename for p in photos)

    def test_date_month(self):
        g = self.run_strategy({"name": "date"})
        self.assertEqual(self.names(g["按日期/2024/2024-05"]), ["IMG_0001 copy.JPG", "IMG_0001.JPG", "IMG_0002.JPG"])
        self.assertIn("按日期/2023/2023-12", g)

    def test_date_season_and_flat(self):
        g = self.run_strategy({"name": "date", "granularity": "season", "nested": False, "prefix": ""})
        self.assertIn("2024 冬", g)  # 2023-12 算 2024 冬
        self.assertIn("2024 春", g)

    def test_location_grid(self):
        g = self.run_strategy({"name": "location"})
        self.assertEqual(list(g), ["按地点/坐标 N35 E135"])

    def test_location_names(self):
        photos = [Photo(id="a", filename="a", country="日本", city="京都"), Photo(id="b", filename="b", country="中国")]
        g = build({"name": "location"}).run(photos)
        self.assertEqual(set(g), {"按地点/日本/京都", "按地点/中国"})

    def test_media_type(self):
        g = self.run_strategy("media_type")
        self.assertEqual(self.names(g["按类型/截图"]), ["IMG_0004.PNG"])
        self.assertEqual(self.names(g["按类型/自拍"]), ["IMG_0003.JPG"])
        self.assertEqual(self.names(g["按类型/实况照片"]), ["IMG_0005.JPG", "IMG_0005.MOV"])
        self.assertNotIn("按类型/视频", g)  # 实况的 MOV 不算普通视频

    def test_duplicates_keeps_one(self):
        g = self.run_strategy("duplicates")
        self.assertEqual(len(g["待清理/重复"]), 1)
        self.assertIn(g["待清理/重复"][0].filename, {"IMG_0001.JPG", "IMG_0001 copy.JPG"})

    def test_similar(self):
        g = self.run_strategy("similar")
        self.assertEqual(len(g), 1)
        (album, items), = g.items()
        self.assertTrue(album.startswith("待清理/相似/001 2024-05-01"))
        self.assertEqual(self.names(items), ["IMG_0001 copy.JPG", "IMG_0001.JPG", "IMG_0002.JPG"])

    def test_events(self):
        g = self.run_strategy({"name": "events", "min_photos": 3})
        self.assertEqual(list(g), ["按事件/2024-05-01"])

    def test_events_span_and_place(self):
        t = datetime(2024, 5, 1, 10)
        photos = [Photo(id=str(i), filename=str(i), date=t + timedelta(hours=6 * i), city="京都") for i in range(5)]
        g = build({"name": "events", "min_photos": 3}).run(photos)
        self.assertEqual(list(g), ["按事件/2024-05-01~05-02 京都"])

    def test_people(self):
        photos = [Photo(id=str(i), filename=str(i), persons=["妈妈"] + (["小明"] if i == 0 else [])) for i in range(3)]
        g = build({"name": "people", "min_count": 2}).run(photos)
        self.assertEqual(list(g), ["按人物/妈妈"])

    def test_large(self):
        photos = [Photo(id="a", filename="a", size=60 * 1024 * 1024), Photo(id="b", filename="b", is_video=True, duration=300)]
        g = build("large").run(photos)
        self.assertEqual([p.id for p in g["待清理/大文件"]], ["a"])
        self.assertEqual([p.id for p in g["待清理/长视频"]], ["b"])

    def test_unknown_option(self):
        with self.assertRaises(ValueError):
            build({"name": "date", "foo": 1})

    def test_presets_build(self):
        for key in PRESETS:
            strategies_from_config({"preset": key})


class TestRules(LibraryTestCase):
    def test_rules(self):
        rules = [
            {"album": "京都/{year}-{month:02d}", "when": {"all": [
                {"field": "latitude", "op": "between", "value": [34.5, 35.5]},
                {"field": "is_video", "op": "eq", "value": False}]}, "stop": True},
            {"album": "竖拍", "when": {"field": "orientation", "op": "eq", "value": "portrait"}},
            {"album": "晚上", "when": {"field": "hour", "op": "gte", "value": 19}},
            {"album": "{camera_model}", "when": {"not": {"field": "camera_model", "op": "exists"}}},
        ]
        g = RulesStrategy(rules).run(list(self.photos().values()))
        self.assertEqual(len(g["京都/2024-05"]), 3)
        self.assertEqual([p.filename for p in g["竖拍"]], ["IMG_0004.PNG"])
        self.assertEqual([p.filename for p in g["晚上"]], ["IMG_0003.JPG"])
        self.assertEqual(sorted(p.filename for p in g["未知"]), ["IMG_0004.PNG", "IMG_0005.MOV"])

    def test_contains_list(self):
        p = Photo(id="a", filename="a", persons=["妈妈", "爸爸"])
        g = RulesStrategy([{"album": "家人", "when": {"field": "persons", "op": "contains", "value": "妈妈"}}]).run([p])
        self.assertIn("家人", g)

    def test_render_unknown(self):
        self.assertEqual(render_album("{country}/{month:02d}", Photo(id="a", filename="a")), "未知/未知")

    def test_parse_strategy_arg(self):
        self.assertEqual(
            parse_strategy_arg("media_type:types=video|selfie"),
            {"name": "media_type", "types": ["video", "selfie"]},
        )
        self.assertEqual(
            parse_strategy_arg("date:granularity=year,nested=false"),
            {"name": "date", "granularity": "year", "nested": False},
        )


class TestPlanAndSink(LibraryTestCase):
    def build_plan(self):
        photos = FolderSource(self.lib).photos()
        info = {"kind": "folder", "path": str(self.lib)}
        return Plan.build(photos, strategies_from_config({"preset": "basic"}), info)

    def test_plan_roundtrip(self):
        plan = self.build_plan()
        path = self.tmp / "plan.json"
        plan.save(path)
        loaded = Plan.load(path)
        self.assertEqual(loaded.albums, plan.albums)
        self.assertIn("按类型/截图", json.loads(path.read_text(encoding="utf-8"))["albums"])

    def test_copy_is_idempotent(self):
        plan = self.build_plan()
        out = self.tmp / "out"
        FolderSink(out, "copy").apply(plan, log=lambda *_: None)
        FolderSink(out, "copy").apply(plan, log=lambda *_: None)
        files = sorted(p.name for p in (out / "按日期" / "2024" / "2024-05").iterdir())
        self.assertEqual(files, ["IMG_0001 copy.JPG", "IMG_0001.JPG", "IMG_0002.JPG"])
        self.assertTrue((self.lib / "IMG_0001.JPG").exists())

    def test_move(self):
        plan = self.build_plan()
        out = self.tmp / "out"
        result = FolderSink(out, "move").apply(plan, log=lambda *_: None)
        self.assertEqual(result["removed"], 7)
        self.assertFalse((self.lib / "IMG_0005.JPG").exists())
        self.assertTrue((out / "按类型" / "实况照片" / "IMG_0005.JPG").exists())
        self.assertTrue((out / "按日期" / "2022" / "2022-07" / "IMG_0005.JPG").exists())

    def test_dry_run(self):
        plan = self.build_plan()
        out = self.tmp / "out"
        FolderSink(out, "copy").apply(plan, dry_run=True, log=lambda *_: None)
        self.assertFalse(out.exists())


class TestCli(LibraryTestCase):
    def test_run_end_to_end(self):
        out = self.tmp / "out"
        cfg = self.tmp / "cfg.yaml"
        cfg.write_text("strategies:\n  - {name: date, granularity: year}\nrules:\n  - album: 自拍合集\n"
                       "    when: {field: is_selfie, op: eq, value: true}\n", encoding="utf-8")
        code = main(["run", "--source", "folder", "--path", str(self.lib), "-c", str(cfg),
                     "-s", "duplicates", "--dest", str(out), "-y"])
        self.assertEqual(code, 0)
        self.assertTrue((out / "自拍合集" / "IMG_0003.JPG").exists())
        self.assertTrue((out / "按日期" / "2023").is_dir())
        self.assertEqual(len(list((out / "待清理" / "重复").iterdir())), 1)

    def test_list(self):
        self.assertEqual(main(["list"]), 0)

    def test_bad_strategy(self):
        self.assertEqual(main(["plan", "--source", "folder", "--path", str(self.lib), "-s", "nope"]), 2)


if __name__ == "__main__":
    unittest.main()
