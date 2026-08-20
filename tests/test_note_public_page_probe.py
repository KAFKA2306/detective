from __future__ import annotations

import unittest

from scripts.note_public_page_probe import public_reaction_count


class PublicReactionCountTest(unittest.TestCase):
    def test_structured_count_is_preferred(self) -> None:
        source = '<script>{"likeCount":42}</script><button>99</button>'
        self.assertEqual(public_reaction_count(source), "42")

    def test_labeled_reaction_button(self) -> None:
        source = '<button aria-label="スキ">1,884</button><button>7</button>'
        self.assertEqual(public_reaction_count(source), "1884")

    def test_duplicate_visible_reaction_count_is_unambiguous(self) -> None:
        source = '<button>674</button><div>article</div><button>674</button>'
        self.assertEqual(public_reaction_count(source), "674")

    def test_ambiguous_unlabeled_button_numbers_are_rejected(self) -> None:
        source = '<button>674</button><button>3</button>'
        self.assertIsNone(public_reaction_count(source))

    def test_no_public_count_returns_none(self) -> None:
        self.assertIsNone(public_reaction_count('<button>スキ</button>'))


if __name__ == "__main__":
    unittest.main()
