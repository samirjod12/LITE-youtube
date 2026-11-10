"""Unit tests for everything that does not need Qt, yt-dlp, mpv or network.
Run:  python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ytlite import blocker, cache, config, db, errors, formats, hwinfo, mpvconf, player, procmem, search  # noqa: E402
from ytlite.paths import Paths, is_within  # noqa: E402


def fmt(fid, h, vcodec="avc1.64001f", acodec="none", fps=30, tbr=500, proto="https", w=None, **kw):
    d = {"format_id": fid, "url": f"https://rr1.googlevideo.com/{fid}", "height": h,
         "width": w or int(h * 16 / 9), "vcodec": vcodec, "acodec": acodec, "fps": fps,
         "tbr": tbr, "protocol": proto, "ext": "mp4"}
    d.update(kw)
    return d


def audio(fid, abr, acodec="mp4a.40.2", **kw):
    d = {"format_id": fid, "url": f"https://rr1.googlevideo.com/{fid}", "vcodec": "none",
         "acodec": acodec, "abr": abr, "tbr": abr, "protocol": "https", "ext": "m4a"}
    d.update(kw)
    return d


class PathsTests(unittest.TestCase):
    def test_layout_and_ensure(self):
        with tempfile.TemporaryDirectory() as t:
            p = Paths(t)
            self.assertEqual(p.ensure(), [])
            for d in ("config", "data", "cache/thumbnails", "cache/metadata", "filters", "mpv", "logs"):
                self.assertTrue((Path(t) / d).is_dir(), d)
            self.assertTrue(p.is_writable())
            self.assertTrue(is_within(p.thumb_dir, p.cache_dir))
            self.assertFalse(is_within(Path(t) / ".." / "x", p.cache_dir))


class ConfigTests(unittest.TestCase):
    def test_defaults_and_profiles(self):
        with tempfile.TemporaryDirectory() as t:
            s = config.Settings(Path(t) / "s.json")
            s.load()
            self.assertEqual(s["profile"], "eco")
            self.assertEqual(s.profile.results, 10)
            self.assertEqual(config.PROFILES["balanced"].results, 15)
            self.assertEqual(config.PROFILES["quality"].results, 20)
            self.assertEqual(s.effective_quality(), 360)
            self.assertFalse(s["adblock"]["enabled"])           # default OFF
            self.assertEqual(s.thumb_limit_bytes(), 30 * 1024 * 1024)

    def test_roundtrip_and_validation(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "s.json"
            s = config.Settings(path)
            s["profile"] = "quality"
            s["volume"] = 999
            s["hwdec"] = "bogus"
            self.assertTrue(s.save())
            s2 = config.Settings(path)
            s2.load()
            self.assertEqual(s2["profile"], "quality")
            self.assertEqual(s2["volume"], 100)
            self.assertEqual(s2["hwdec"], "auto")

    def test_corrupt_file_falls_back(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "s.json"
            path.write_text("{not json", encoding="utf-8")
            s = config.Settings(path)
            s.load()
            self.assertEqual(s["profile"], "eco")
            self.assertTrue(s.last_error)
            self.assertTrue((Path(t) / "s.json.bad").exists())

    def test_wrong_types_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "s.json"
            path.write_text(json.dumps({"volume": "loud", "auto_play": 1, "unknown": 5,
                                        "cache": {"thumb_mb": 50}}), encoding="utf-8")
            s = config.Settings(path)
            s.load()
            self.assertEqual(s["volume"], 80)
            self.assertTrue(s["auto_play"] is True)
            self.assertEqual(s["cache"]["thumb_mb"], 50)
            self.assertNotIn("unknown", s.data)

    def test_save_failure_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as t:
            blocker_file = Path(t) / "iamafile"
            blocker_file.write_text("x")          # a file where a folder is needed: fails on every OS
            s = config.Settings(blocker_file / "sub" / "s.json")
            self.assertFalse(s.save())
            self.assertTrue(s.last_error)

    def test_celeron_preset(self):
        s = config.Settings(Path("x.json"))
        s["profile"] = "quality"
        s["default_quality"] = 1080
        s.apply_celeron_847_preset()
        self.assertEqual((s["profile"], s["default_quality"], s["codec_preference"]), ("eco", 360, "h264"))


class DbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = db.Storage(Path(self.tmp.name) / "h.db")
        self.assertTrue(self.s.open())
        self.v = {"id": "dQw4w9WgXcQ", "title": "T", "channel": "C", "channel_id": "UC1",
                  "duration": 100, "thumb_url": "https://i.ytimg.com/x.jpg"}

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def test_search_history(self):
        self.s.add_search("cats")
        self.s.add_search("dogs")
        self.s.add_search("cats")
        self.assertEqual(self.s.recent_searches(), ["cats", "dogs"])
        self.s.delete_search("dogs")
        self.assertEqual(self.s.recent_searches(), ["cats"])
        self.s.clear_searches()
        self.assertEqual(self.s.recent_searches(), [])

    def test_history_and_remove(self):
        self.s.add_history(self.v)
        self.s.add_history(self.v)                      # no duplicates
        self.assertEqual(self.s.history_count(), 1)
        self.assertEqual(self.s.history()[0]["id"], self.v["id"])
        self.s.remove_history(self.v["id"])
        self.assertEqual(self.s.history_count(), 0)

    def test_watch_later(self):
        self.assertTrue(self.s.add_watch_later(self.v))
        self.assertFalse(self.s.add_watch_later(self.v))
        self.assertTrue(self.s.in_watch_later(self.v["id"]))
        self.s.remove_watch_later(self.v["id"])
        self.assertFalse(self.s.in_watch_later(self.v["id"]))

    def test_playlists(self):
        pid = self.s.create_playlist("Music")
        with self.assertRaises(db.StorageError):
            self.s.create_playlist("Music")
        with self.assertRaises(db.StorageError):
            self.s.create_playlist("  ")
        self.assertTrue(self.s.add_to_playlist(pid, self.v))
        self.assertFalse(self.s.add_to_playlist(pid, self.v))
        self.assertEqual(self.s.playlists()[0]["count"], 1)
        self.assertEqual(self.s.playlist_items(pid)[0]["id"], self.v["id"])
        self.s.rename_playlist(pid, "Tunes")
        self.assertEqual(self.s.playlists()[0]["name"], "Tunes")
        self.s.remove_from_playlist(pid, self.v["id"])
        self.assertEqual(self.s.playlist_count(pid), 0)
        self.s.delete_playlist(pid)
        self.assertEqual(self.s.playlists(), [])

    def test_channels_and_clear_all(self):
        ch = {"id": "UC1", "title": "Chan", "url": "https://www.youtube.com/channel/UC1"}
        self.assertTrue(self.s.save_channel(ch))
        self.assertFalse(self.s.save_channel(ch))
        self.assertEqual(self.s.channels()[0]["kind"], "channel")
        self.s.add_history(self.v)
        self.s.add_search("x")
        self.s.clear_all()
        self.assertEqual((self.s.history_count(), self.s.recent_searches(), self.s.channels()), (0, [], []))

    def test_history_cap(self):
        for i in range(db.MAX_HISTORY + 5):
            self.s.add_history({**self.v, "id": f"{i:011d}"})
        self.assertEqual(self.s.history_count(), db.MAX_HISTORY)

    def test_failure_is_contained(self):
        self.s.close()
        with self.assertRaises(db.StorageError):
            self.s.add_search("x")
        blocker_file = Path(self.tmp.name) / "iamafile"
        blocker_file.write_text("x")
        bad = db.Storage(blocker_file / "sub" / "h.db")
        self.assertFalse(bad.open())
        self.assertFalse(bad.available)


class CacheTests(unittest.TestCase):
    def test_eviction_keeps_under_limit(self):
        with tempfile.TemporaryDirectory() as t:
            c = cache.ThumbnailCache(Path(t), lambda: 10_000)
            for i in range(30):
                self.assertTrue(c.write(f"k{i}", b"x" * 1000))
                time.sleep(0.002)
            self.assertLessEqual(c.size(), 10_000)
            self.assertIsNotNone(c.read("k29"))      # newest survives
            self.assertIsNone(c.read("k0"))          # oldest evicted

    def test_clear_and_size(self):
        with tempfile.TemporaryDirectory() as t:
            c = cache.ThumbnailCache(Path(t), lambda: 10**6)
            c.write("a", b"12345")
            self.assertEqual(c.size(), 5)
            self.assertEqual(c.clear(), 1)
            self.assertEqual(c.size(), 0)

    def test_metadata_ttl(self):
        with tempfile.TemporaryDirectory() as t:
            m = cache.MetadataCache(Path(t), lambda: 10**6)
            m.put("q", [{"a": 1}])
            self.assertEqual(m.get("q", 60), [{"a": 1}])
            time.sleep(0.05)
            self.assertIsNone(m.get("q", 0.01))
            self.assertIsNone(m.get("missing", 60))

    def test_corrupt_metadata_is_miss(self):
        with tempfile.TemporaryDirectory() as t:
            m = cache.MetadataCache(Path(t), lambda: 10**6)
            m.write("q", b"\xff\xfe not json")
            self.assertIsNone(m.get("q", 60))

    def test_logging_never_raises(self):
        with tempfile.TemporaryDirectory() as t:
            lg = cache.setup_logging(Path(t) / "logs" / "a.log", 2 * 1024 * 1024)
            lg.warning("hello")
            for h in lg.handlers:
                h.flush()
            self.assertTrue((Path(t) / "logs" / "a.log").exists())
            for h in list(lg.handlers):          # Windows cannot delete a file that is still open
                h.close()
                lg.removeHandler(h)


class BlockerTests(unittest.TestCase):
    def make(self, block="", allow="", downloaded=""):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        d = Path(t.name)
        (d / "b.txt").write_text(block)
        (d / "a.txt").write_text(allow)
        (d / "d.txt").write_text(downloaded)
        b = blocker.DomainBlocker(d / "b.txt", d / "a.txt", d / "d.txt")
        b.reload()
        return b

    def test_off_by_default_never_blocks(self):
        b = self.make("ads.example.com\n")
        self.assertFalse(b.enabled)
        self.assertFalse(b.check_url("https://ads.example.com/x"))
        self.assertEqual(b.checked_count, 0)

    def test_blocks_subdomains_and_counts(self):
        b = self.make("example.com\n")
        b.enabled = True
        self.assertTrue(b.check_url("https://a.b.example.com/x"))
        self.assertFalse(b.check_url("https://notexample.com/"))
        self.assertEqual((b.checked_count, b.blocked_count), (2, 1))

    def test_allowlist_wins_and_protected(self):
        b = self.make("example.com\ngooglevideo.com\nyoutube.com\n", "good.example.com\n")
        b.enabled = True
        self.assertFalse(b.check_url("https://good.example.com/"))
        self.assertTrue(b.check_url("https://bad.example.com/"))
        self.assertFalse(b.check_url("https://rr1.googlevideo.com/videoplayback"))
        self.assertFalse(b.check_url("https://www.youtube.com/watch"))

    def test_parse_formats(self):
        text = ("# comment\n0.0.0.0 ads.one.com\n127.0.0.1 localhost\n||two.net^\n"
                "three.org # trailing\n*.four.io\nnot a domain!!\n! adblock comment\n"
                "0.0.0.0 youtube.com\n")
        got = blocker.parse_domains(text)
        self.assertEqual(got, {"ads.one.com", "two.net", "three.org", "four.io"})

    def test_update_rejects_non_https(self):
        b = self.make()
        with self.assertRaises(errors.YtLiteError):
            b.update_from_url("http://example.com/list.txt")
        with self.assertRaises(errors.YtLiteError):
            b.update_from_url("file:///etc/passwd")

    def test_save_custom_reloads(self):
        b = self.make()
        b.save_custom("tracker.test\n", "ok.tracker.test\n")
        b.enabled = True
        self.assertTrue(b.host_is_blocked("x.tracker.test"))
        self.assertFalse(b.host_is_blocked("ok.tracker.test"))


class ErrorTests(unittest.TestCase):
    def test_classification(self):
        cases = {
            "ERROR: [youtube] abcdefghijk: Private video. Sign in if you've been granted access": "private",
            "ERROR: Sign in to confirm your age. This video may be inappropriate for some users.": "age",
            "ERROR: Video unavailable. The uploader has not made this video available in your country": "region",
            "ERROR: Video unavailable": "unavailable",
            "ERROR: Sign in to confirm you're not a bot": "bot",
            "ERROR: Unable to extract initial data; please report this issue": "update",
            "<urlopen error [Errno 11001] getaddrinfo failed>": "network",
            "ERROR: Unable to download webpage: The read operation timed out": "network",
            "ERROR: Requested format is not available": "format",
            "This video is DRM protected": "drm",
        }
        for raw, kind in cases.items():
            self.assertEqual(errors.classify(raw)[0], kind, raw)

    def test_unknown_and_exceptions(self):
        self.assertEqual(errors.classify("weird thing")[0], "unknown")
        self.assertEqual(errors.from_exception(TimeoutError()).kind, "network")
        e = errors.YtLiteError("x", "m")
        self.assertIs(errors.from_exception(e), e)
        self.assertEqual(errors.from_exception(PermissionError("no")).kind, "permission")


class FormatTests(unittest.TestCase):
    def sample(self):
        return [
            fmt("160", 144, tbr=100), fmt("133", 240, tbr=200), fmt("134", 360, tbr=400),
            fmt("243", 360, vcodec="vp09.00.21.08", tbr=300),
            fmt("135", 480, tbr=700), fmt("136", 720, tbr=1200),
            fmt("247", 720, vcodec="vp09.00.31.08", tbr=900),
            fmt("298", 720, fps=60, tbr=2000),
            fmt("137", 1080, tbr=2500),
            fmt("399", 1080, vcodec="av01.0.08M.08", tbr=1500),
            fmt("18", 360, acodec="mp4a.40.2", tbr=500),
            fmt("sb0", 90, vcodec="none", acodec="none", ext="mhtml"),
            fmt("hls", 720, proto="m3u8_native"),
            audio("139", 48), audio("140", 129), audio("251", 160, acodec="opus"),
        ]

    def test_codec_family(self):
        self.assertEqual(formats.codec_family("avc1.4d401f"), "h264")
        self.assertEqual(formats.codec_family("vp09.00.40.08"), "vp9")
        self.assertEqual(formats.codec_family("av01.0.05M.08"), "av1")
        self.assertEqual(formats.codec_family("hvc1.1.6.L93"), "hevc")
        self.assertEqual(formats.codec_family("none"), "none")
        self.assertEqual(formats.codec_family(None), "none")

    def test_prefers_h264_and_30fps(self):
        opts = {o.height: o for o in formats.choose_options(self.sample(), "h264", 130)}
        self.assertEqual(sorted(opts), [144, 240, 360, 480, 720, 1080])
        self.assertEqual(opts[720].video_id, "136")          # not VP9 (cheaper) nor 60 fps
        self.assertEqual(opts[1080].video_id, "137")
        self.assertTrue(all(o.codec == "h264" for o in opts.values()))
        self.assertEqual(opts[720].audio_id, "140")          # AAC within cap, not Opus 160
        self.assertEqual(opts[720].audio_url, "https://rr1.googlevideo.com/140")

    def test_progressive_has_no_separate_audio(self):
        only = [fmt("18", 360, acodec="mp4a.40.2")]
        o = formats.choose_options(only)[0]
        self.assertIsNone(o.audio_url)
        self.assertEqual(o.note, "")

    def test_no_h264_gets_a_warning_note(self):
        vp9 = [fmt("247", 720, vcodec="vp09.00.31.08"), audio("140", 129)]
        o = formats.choose_options(vp9, "h264")[0]
        self.assertEqual(o.codec, "vp9")
        self.assertIn("No H.264", o.note)

    def test_any_codec_pref_picks_highest_bitrate(self):
        o = {x.height: x for x in formats.choose_options(self.sample(), "any")}
        self.assertEqual(o[1080].video_id, "137")

    def test_streaming_protocols_and_drm_excluded(self):
        fl = [fmt("hls", 720, proto="m3u8_native"), fmt("d", 480, has_drm=True)]
        self.assertEqual(formats.choose_options(fl), [])

    def test_portrait_video_uses_short_side(self):
        o = formats.choose_options([fmt("p", 1920, w=1080), audio("140", 129)])
        self.assertEqual(o[0].height, 1080)

    def test_bitrate_is_labelled_reported(self):
        o = formats.choose_options([fmt("136", 720, tbr=1200)])[0]
        self.assertIn("reported", o.bitrate_label)
        o2 = formats.choose_options([fmt("136", 720, tbr=None)])[0]
        self.assertEqual(o2.bitrate_label, "n/a")

    def test_pick_default(self):
        opts = formats.choose_options(self.sample())
        self.assertEqual(formats.pick_default(opts, 360).height, 360)
        self.assertEqual(formats.pick_default(opts, 600).height, 480)
        self.assertEqual(formats.pick_default([o for o in opts if o.height >= 480], 240).height, 480)
        self.assertIsNone(formats.pick_default([], 360))

    def test_formatting_helpers(self):
        self.assertEqual(formats.fmt_duration(65), "1:05")
        self.assertEqual(formats.fmt_duration(3725), "1:02:05")
        self.assertEqual(formats.fmt_duration(None), "")
        self.assertEqual(formats.fmt_views(1500), "1.5K views")
        self.assertEqual(formats.fmt_views(2_500_000), "2.5M views")
        self.assertEqual(formats.lower_height(720), 480)
        self.assertIsNone(formats.lower_height(144))


class SearchNormalizeTests(unittest.TestCase):
    def test_video_entry(self):
        e = {"_type": "url", "ie_key": "Youtube", "id": "dQw4w9WgXcQ", "title": "Hello",
             "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "duration": 212,
             "view_count": 1234, "channel": "Chan", "channel_id": "UCabc",
             "thumbnails": [{"url": "https://i.ytimg.com/a.jpg", "width": 168},
                            {"url": "https://i.ytimg.com/b.jpg", "width": 336}]}
        v = search.normalize_entry(e, 168)
        self.assertEqual((v.kind, v.id, v.duration, v.views), ("video", "dQw4w9WgXcQ", 212, 1234))
        self.assertEqual(v.thumb_url, "https://i.ytimg.com/a.jpg")
        self.assertEqual(search.normalize_entry(e, 300).thumb_url, "https://i.ytimg.com/b.jpg")

    def test_channel_entry_and_playlist_skipped(self):
        ch = {"ie_key": "YoutubeTab", "id": "UCabc", "title": "My Channel",
              "url": "https://www.youtube.com/channel/UCabc"}
        v = search.normalize_entry(ch)
        self.assertEqual((v.kind, v.title), ("channel", "My Channel"))
        pl = {"ie_key": "YoutubeTab", "id": "PL1", "title": "List",
              "url": "https://www.youtube.com/playlist?list=PL1"}
        self.assertIsNone(search.normalize_entry(pl))

    def test_malformed_entries_are_dropped_safely(self):
        for bad in (None, 5, "x", [], {}, {"id": "short", "title": "t"},
                    {"id": "dQw4w9WgXcQ"}, {"id": "dQw4w9WgXcQ", "title": "[Private video]"},
                    {"id": "dQw4w9WgXcQ", "title": "ok", "duration": "abc", "view_count": [1]}):
            r = search.normalize_entry(bad)
            if r is not None:                 # the last one is valid but with junk numbers
                self.assertIsNone(r.duration)
                self.assertIsNone(r.views)

    def test_non_https_thumbnail_rejected_and_fallback(self):
        e = {"id": "dQw4w9WgXcQ", "title": "t", "thumbnails": [{"url": "http://evil/x.jpg", "width": 9}]}
        self.assertEqual(search.normalize_entry(e).thumb_url,
                         "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg")

    def test_dedupe(self):
        e = {"id": "dQw4w9WgXcQ", "title": "t"}
        self.assertEqual(len(search.normalize_entries([e, dict(e), None], 168)), 1)

    def test_input_validation_does_not_need_ytdlp(self):
        s = search.SearchService()
        with self.assertRaises(errors.YtLiteError):
            s.search_videos("  ", 1, 10, 168)
        with self.assertRaises(errors.YtLiteError):
            s.extract_streams("bad id", "h264", 130)
        with self.assertRaises(errors.YtLiteError):
            s.channel_videos("https://evil.example/channel/x", 1, 10, 168)

    def test_missing_ytdlp_is_a_friendly_error(self):
        try:
            import yt_dlp  # noqa: F401
            self.skipTest("yt-dlp is installed")
        except ImportError:
            pass
        with self.assertRaises(errors.YtLiteError) as cm:
            search.SearchService().search_videos("cats", 1, 10, 168)
        self.assertEqual(cm.exception.kind, "missing_dep")


class MpvTests(unittest.TestCase):
    OPTS = "Options:\n --hwdec=<no|auto|...>\n --cache=<yes|no|auto>\n --cache-secs=<sec>\n" \
           " --vd-lavc-threads=<N>\n --vd-lavc-fast\n --framedrop=<no|vo|...>\n"

    def test_parse_options_and_conf(self):
        s = mpvconf.parse_list_options(self.OPTS)
        self.assertIn("cache-secs", s)
        self.assertEqual(mpvconf.parse_conf("# c\nhwdec=auto\n\ncache=yes\nbadline!!\nfoo\n"),
                         [("hwdec", "auto"), ("cache", "yes"), ("foo", "yes")])

    def test_unsupported_options_not_forced(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "mpv.conf"
            p.write_text("hwdec=auto\ncache=yes\nscale=bilinear\nframedrop=vo\n")
            args, skipped = mpvconf.conf_args(p, mpvconf.parse_list_options(self.OPTS))
            self.assertEqual(args, ["--cache=yes", "--framedrop=vo"])
            self.assertEqual(skipped, ["scale"])
            args, skipped = mpvconf.conf_args(p, None)       # cannot list -> pass nothing
            self.assertEqual(args, [])

    def test_default_conf_matches_brief(self):
        keys = dict(mpvconf.parse_conf(mpvconf.DEFAULT_MPV_CONF))
        self.assertEqual(keys["hwdec"], "auto")
        self.assertEqual(keys["demuxer-max-bytes"], "48MiB")
        self.assertEqual(keys["demuxer-max-back-bytes"], "16MiB")
        self.assertEqual(keys["cache-secs"], "15")
        self.assertEqual(keys["video-sync"], "audio")

    def test_ensure_conf_creates_once(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "mpv" / "mpv.conf"
            mpvconf.ensure_conf(p)
            self.assertTrue(p.exists())
            p.write_text("hwdec=no\n")
            mpvconf.ensure_conf(p)
            self.assertEqual(p.read_text(), "hwdec=no\n")

    def test_hwdec_help_parse(self):
        out = "Valid values for hwdec:\n  no\n  auto\n  auto-copy\n  d3d11va\n  dxva2-copy\n"
        self.assertTrue({"auto", "auto-copy", "d3d11va"} <= mpvconf.parse_hwdec_list(out))


class PlayerTests(unittest.TestCase):
    def opt(self, audio_url="https://a/aud", ua="UA/1"):
        return formats.StreamOption(720, 1280, 30, "h264", "avc1", 1200, "https://v/vid", "136",
                                    audio_url, "140", "mp4a", 129, {"User-Agent": ua} if ua else {})

    def cmd(self, **over):
        kw = dict(conf_args=["--cache=yes"], hwdec="auto", speed=1.0, volume=80, fullscreen=False,
                  decoder_threads=2, sw_assist=False, start_seconds=0, supported=None, hwdecs=None)
        kw.update(over)
        return player.build_mpv_command(Path("/x/mpv"), self.opt(), "My Title", "/tmp/s.sock", **kw)

    def test_command_is_argv_list_with_separator(self):
        c = self.cmd()
        self.assertIsInstance(c, list)
        self.assertEqual(c[0], str(Path("/x/mpv")))
        self.assertIn("--no-config", c)
        self.assertIn("--hwdec=auto", c)
        self.assertIn("--audio-file=https://a/aud", c)
        self.assertIn("--ytdl=no", c)
        self.assertEqual(c[-2:], ["--", "https://v/vid"])
        self.assertIn("--user-agent=UA/1", c)

    def test_hwdec_choices(self):
        self.assertIn("--hwdec=no", self.cmd(hwdec="no"))
        self.assertIn("--hwdec=auto-copy", self.cmd(hwdec="auto-copy", hwdecs={"auto", "auto-copy"}))
        # unsupported on this mpv build -> not forced
        self.assertFalse([a for a in self.cmd(hwdec="auto-copy", hwdecs={"auto"}) if a.startswith("--hwdec")])

    def test_unsupported_options_skipped_and_resume(self):
        c = self.cmd(sw_assist=True, supported={"vd-lavc-fast"}, start_seconds=95.7)
        self.assertIn("--vd-lavc-fast", c)
        self.assertNotIn("--vd-lavc-skiploopfilter=nonref", c)
        self.assertNotIn("--vd-lavc-threads=2", c)
        self.assertIn("--start=95", c)

    def test_no_audio_file_for_progressive_and_newline_ua_ignored(self):
        o = self.opt(audio_url=None, ua="bad\nUA")
        c = player.build_mpv_command(Path("m"), o, "t", "p", conf_args=[], hwdec="auto", speed=1,
                                     volume=10, fullscreen=True, decoder_threads=0, sw_assist=False)
        self.assertFalse([a for a in c if a.startswith(("--audio-file", "--user-agent"))])
        self.assertIn("--fullscreen", c)

    def test_title_sanitised(self):
        self.assertNotIn("\n", player.safe_title("a\nb\x00c"))
        self.assertEqual(player.safe_title(""), "YouTube Lite")

    def test_ipc_protocol(self):
        p = player.IpcProtocol()
        rid, raw = p.command("get_property", "time-pos")
        self.assertEqual(json.loads(raw)["command"], ["get_property", "time-pos"])
        self.assertEqual(json.loads(raw)["request_id"], rid)
        self.assertEqual(p.command("quit")[0], rid + 1)
        msgs = p.feed(b'{"event":"x"}\n{"error":"success","data":4.5,"request_id":1}\n{"par')
        self.assertEqual(len(msgs), 2)
        self.assertEqual(p.feed(b'tial":1}\nnot json\n'), [{"partial": 1}])

    def test_ipc_endpoint(self):
        value, name = player.ipc_endpoint(1234)
        self.assertIn("1234", value)
        self.assertIn("1234", name)

    def test_health_software_decode_advice_is_given_once(self):
        h = player.PlaybackHealth(height=720)
        r = h.assess({"time-pos": 5, "hwdec-current": "no", "estimated-vf-fps": 30})
        self.assertEqual((r.decode, r.hardware), ("software", False))
        self.assertIn("480p", r.advice)
        self.assertEqual(h.assess({"time-pos": 6, "hwdec-current": "no"}).advice, "")

    def test_health_hardware_and_drops(self):
        h = player.PlaybackHealth(height=480)
        r = h.assess({"time-pos": 3, "hwdec-current": "d3d11va"})
        self.assertEqual((r.decode, r.hardware, r.advice), ("hardware (d3d11va)", True, ""))
        r = h.assess({"time-pos": 20, "hwdec-current": "d3d11va", "estimated-vf-fps": 30,
                      "frame-drop-count": 60, "decoder-frame-drop-count": 10})
        self.assertEqual(r.dropped, 70)
        self.assertAlmostEqual(r.drop_percent, 11.7, places=1)
        self.assertIn("360p", r.advice)

    def test_health_unknown_before_playback_starts(self):
        r = player.PlaybackHealth(height=720).assess({"time-pos": 0.5})
        self.assertEqual((r.decode, r.hardware, r.advice), ("unknown", None, ""))

    def test_exit_messages(self):
        self.assertIn("expired", player.exit_message(2, "boom"))
        self.assertEqual(player.exit_message(0, "x"), "Playback finished.")
        self.assertTrue(player.exit_message(1, "gpu error").endswith("gpu error"))


class HwinfoTests(unittest.TestCase):
    def test_celeron_847_generation(self):
        g = hwinfo.guess_generation("Intel(R) Celeron(R) CPU 847 @ 1.10GHz")
        self.assertIn("Sandy Bridge", g["generation"])
        self.assertIn("H.264", g["expected_hw"])
        self.assertIn("VP9", g["no_hw"])

    def test_other_cpus(self):
        self.assertIn("Ivy", hwinfo.guess_generation("Intel Core i5-3210M")["generation"])
        self.assertEqual(hwinfo.guess_generation("AMD Ryzen 5 5600")["generation"], "unknown")

    def test_gpu_json(self):
        one = '{"Name":"Intel(R) HD Graphics","DriverVersion":"9.17.10.4229"}'
        self.assertEqual(hwinfo.parse_gpu_json(one)[0]["driver"], "9.17.10.4229")
        two = '[{"Name":"A","DriverVersion":"1"},{"Name":"B"}]'
        self.assertEqual(len(hwinfo.parse_gpu_json(two)), 2)
        self.assertEqual(hwinfo.parse_gpu_json("garbage"), [])

    def test_describe_makes_no_verification_claim(self):
        txt = hwinfo.describe(hwinfo.detect_system())
        self.assertIn("CPU:", txt)
        self.assertIn("player page", txt)


class ProcmemTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux") or os.name == "nt", "needs /proc or Windows")
    def test_own_process(self):
        m = procmem.process_memory()
        self.assertIsNotNone(m)
        self.assertGreater(m["working_set_mb"], 1)

    def test_bad_pid(self):
        self.assertIsNone(procmem.process_memory(2**22 + 12345))


if __name__ == "__main__":
    unittest.main()
