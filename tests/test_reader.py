"""The reader against a stand-in of the official address."""

from __future__ import annotations

import contextlib
import io
import socket
import unittest
from unittest import mock

import noun_probe
from tests.standin import StandIn, free_port, publication


class ReaderTestCase(unittest.TestCase):
    """Points the reader at a fresh stand-in serving one publication."""

    def setUp(self):
        self.standin = StandIn().__enter__()
        self.addCleanup(self.standin.__exit__, None, None, None)
        self.addCleanup(setattr, noun_probe, "OFFICIAL_ADDRESS", noun_probe.OFFICIAL_ADDRESS)
        noun_probe.OFFICIAL_ADDRESS = self.standin.base
        noun_probe._held.clear()
        self.addCleanup(noun_probe._held.clear)
        self.standin.serve("source.json", publication())

    def nowhere(self):
        """Point the reader at a port nothing listens on."""
        noun_probe.OFFICIAL_ADDRESS = "http://127.0.0.1:{0}/tools/noun-probe/".format(
            free_port()
        )

    def ask_recorder(self, answer="report"):
        calls = []

        def ask(text):
            calls.append(text)
            return answer

        return ask, calls


class ReadTests(ReaderTestCase):
    def test_read_returns_the_publication(self):
        publication_read = noun_probe.read()
        self.assertEqual(publication_read.edition, "1")
        self.assertEqual(publication_read.modes, ("AUDIT", "VISION"))
        self.assertEqual(publication_read.words, "STAND-IN WORDS")

    def test_words_and_credit_come_from_the_source(self):
        self.assertEqual(noun_probe.words(), "STAND-IN WORDS")
        self.assertEqual(
            noun_probe.credit().splitlines(),
            [
                "Created by Carl D. Hildebrandt · Westfield Innovations LLC",
                "Official Noun Probe: https://azus.ai/tools/noun-probe/",
                "Edition used: 1",
                "More Westfield tools: https://azus.ai/tools/",
            ],
        )

    def test_integer_edition_reads_the_numbered_address(self):
        self.standin.serve("editions/1/source.json", publication())
        self.assertEqual(noun_probe.read(1).edition, "1")
        self.assertIn("/tools/noun-probe/editions/1/source.json", self.standin.requests)

    def test_bad_edition_name_requests_nothing(self):
        with self.assertRaises(ValueError):
            noun_probe.read("../x")
        self.assertEqual(self.standin.requests, [])


class StopTests(ReaderTestCase):
    def test_not_https_stops_before_any_request(self):
        noun_probe.OFFICIAL_ADDRESS = "http://azus.ai/tools/noun-probe/"
        with self.assertRaises(noun_probe.NounProbeUnavailable):
            noun_probe.read()
        self.assertEqual(self.standin.requests, [])

    def test_unreachable_source_stops(self):
        self.nowhere()
        with self.assertRaises(noun_probe.NounProbeUnavailable) as stopped:
            noun_probe.read()
        self.assertIn("Nothing was run", str(stopped.exception))

    def test_redirect_to_another_place_stops(self):
        self.standin.serve(
            "source.json",
            b"",
            status=302,
            headers={"Location": "http://localhost:{0}/x".format(self.standin.port)},
        )
        with self.assertRaises(noun_probe.NounProbeUnavailable):
            noun_probe.read()

    def test_redirect_on_the_same_host_is_followed(self):
        self.standin.serve(
            "source.json",
            b"",
            status=301,
            headers={"Location": self.standin.base + "current.json"},
        )
        self.standin.serve("current.json", publication())
        self.assertEqual(noun_probe.read().edition, "1")

    def test_answer_over_two_megabytes_stops(self):
        self.standin.serve("source.json", b" " * (noun_probe.MAX_BYTES + 1))
        with self.assertRaises(noun_probe.NounProbeUnavailable):
            noun_probe.read()

    def test_html_answer_stops(self):
        self.standin.serve("source.json", b"<!DOCTYPE html><html><body>app</body></html>")
        with self.assertRaises(noun_probe.NounProbeUnavailable):
            noun_probe.read()

    def test_undeclared_boundary_or_mode_runs_nothing(self):
        ask, calls = self.ask_recorder()
        with self.assertRaises(ValueError):
            noun_probe.run(document="d", mode="", boundary="b", ask=ask)
        with self.assertRaises(ValueError):
            noun_probe.run(document="d", mode="AUDIT", boundary=" ", ask=ask)
        self.assertEqual(calls, [])

    def test_unknown_mode_runs_nothing(self):
        ask, calls = self.ask_recorder()
        with self.assertRaises(ValueError):
            noun_probe.run(document="d", mode="REVIEW", boundary="b", ask=ask)
        self.assertEqual(calls, [])

    def test_mode_is_case_insensitive(self):
        self.assertIn("DECLARED MODE: AUDIT", noun_probe.prompt("d", "audit", "b"))


class HoldTests(ReaderTestCase):
    def test_one_reading_is_held_for_five_minutes(self):
        clock = [0.0]
        with mock.patch.object(noun_probe.time, "monotonic", lambda: clock[0]):
            noun_probe.read()
            clock[0] = 299.0
            noun_probe.read()
            clock[0] = 301.0
            noun_probe.read()
        self.assertEqual(len(self.standin.requests), 2)

    def test_fresh_reads_again(self):
        noun_probe.read()
        noun_probe.read(fresh=True)
        self.assertEqual(len(self.standin.requests), 2)


class BoundaryTests(ReaderTestCase):
    def test_writes_nothing_to_disk(self):
        with mock.patch("builtins.open", side_effect=AssertionError("opened a file")):
            report = noun_probe.run(
                document="d", mode="AUDIT", boundary="b", ask=lambda text: "report"
            )
        self.assertTrue(report.startswith("report"))

    def test_contacts_only_the_official_address(self):
        reached = []
        real = socket.create_connection

        def connect(address, *args, **kwargs):
            reached.append(address[:2])
            return real(address, *args, **kwargs)

        with mock.patch("socket.create_connection", connect):
            noun_probe.run(document="d", mode="AUDIT", boundary="b", ask=lambda text: "r")
        self.assertTrue(reached)
        self.assertEqual(set(reached), {("127.0.0.1", self.standin.port)})

    def test_request_carries_no_document(self):
        noun_probe.run(document="SECRET-DOC", mode="AUDIT", boundary="b", ask=lambda t: "r")
        sent = " ".join(self.standin.requests) + " ".join(
            " ".join("{0}: {1}".format(k, v) for k, v in h.items())
            for h in self.standin.headers
        )
        self.assertNotIn("SECRET-DOC", sent)


class MainTests(ReaderTestCase):
    def test_main_prints_what_it_read(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(noun_probe.main([]), 0)
        printed = out.getvalue()
        self.assertIn("Edition:           1", printed)
        self.assertIn("Terms of use:", printed)
        self.assertIn("Azus", printed)

    def test_main_reports_unreachable_source(self):
        self.nowhere()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(noun_probe.main([]), 1)
        self.assertIn(noun_probe.CREATOR_LINE, err.getvalue())


if __name__ == "__main__":
    unittest.main()
