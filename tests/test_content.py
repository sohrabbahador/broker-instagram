import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import content as c

SAMPLE = """#رهن_اجاره «منطقه ۵ تهران»
کد ۱۲۰۴
📍موقعیت: *جنت‌آباد*
📏 متراژ: * ۹۵ متر | ۲ خواب *
📞 *مشاهده تصاویر بیشتر*
📱 09123692401
تلفن2: ۰۹۰۰۳۶۹۲۴۰۱
نام مالک: آقای الف
آدرس دقیق: خیابان فلان پلاک ۱۲
"""

class T(unittest.TestCase):
    def test_sanitize_removes_private(self):
        out = c.sanitize_public_text(SAMPLE)
        for bad in ("0912", "۰۹۰۰", "مالک", "پلاک", "*"):
            self.assertNotIn(bad, out)
        self.assertIn("جنت‌آباد", out)

    def test_caption_limits_and_no_phone(self):
        doc = {"kind": "فروش", "khab": "۲ خواب", "meter": 95, "location": "جنت‌آباد",
               "price": 3_200_000_000, "id": 7}
        cap = c.build_caption(doc, "https://ble.ir/BROKER_amlak", ai_hook="آپارتمان نورگیر در دل جنت‌آباد")
        self.assertLessEqual(len(cap), 2200)
        self.assertLessEqual(cap.count("#"), 30)
        self.assertIn("۳ میلیارد و ۲۰۰ میلیون تومان", cap)
        self.assertIsNone(c.PHONE.search(c.fa_to_en(cap)))

    def test_hook_with_phone_is_dropped(self):
        cap = c.build_caption({"kind": "فروش", "id": 1}, "u", ai_hook="زنگ بزن 09121234567")
        self.assertNotIn("0912", c.fa_to_en(cap))

    def test_intents(self):
        self.assertEqual(c.classify("قیمتش چنده؟"), "price")
        self.assertEqual(c.classify("شماره تماس بدید"), "phone")
        self.assertEqual(c.classify("فالوور رایگان https://x.com"), "spam")
        self.assertTrue(c.needs_human("visit"))
        self.assertEqual(c.extract_phone("۰۹۱۲۱۲۳۴۵۶۷"), "09121234567")

if __name__ == "__main__":
    unittest.main()
