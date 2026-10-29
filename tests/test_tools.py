"""Tests with no network and no models. They run with the standard library:

    python3 -m unittest discover -s tests -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unicodedata
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
EX_ES = os.path.join(ROOT, "examples", "es")
EX_EN = os.path.join(ROOT, "examples", "en")
ORIGINAL = os.path.join(EX_ES, "original.txt")
REWRITTEN = os.path.join(EX_ES, "1-rewritten.txt")
FINAL = os.path.join(EX_ES, "2-final.txt")
CONCEPTS = os.path.join(EX_ES, "concepts.txt")
ORIGINAL_EN = os.path.join(EX_EN, "original.txt")
REWRITTEN_EN = os.path.join(EX_EN, "1-rewritten.txt")
FINAL_EN = os.path.join(EX_EN, "2-final.txt")
CONCEPTS_EN = os.path.join(EX_EN, "concepts.txt")
PAPER = os.path.join(ROOT, "examples", "latex", "paper.tex")
PAPER_PDF = os.path.join(ROOT, "examples", "latex", "paper.pdf")
HAS_PDFLATEX = bool(shutil.which("pdflatex"))
CAN_READ_PDF = bool(shutil.which("pdftotext"))

sys.path.insert(0, SCRIPTS)
import blocks  # noqa: E402
import clean  # noqa: E402
import check  # noqa: E402
import convert  # noqa: E402
import fix  # noqa: E402
import join  # noqa: E402
import latex  # noqa: E402
import rewrite  # noqa: E402
import tells  # noqa: E402
import word  # noqa: E402


def run(*args, **kw):
    # The child writes UTF-8 too: on Windows it would write cp1252 and «» or ñ would break.
    kw["env"] = dict(kw.get("env") or os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          cwd=ROOT, **kw)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def script(name):
    return os.path.join(SCRIPTS, name)


class Check(unittest.TestCase):
    def test_example_keeps_every_concept(self):
        r = run(sys.executable, script("check.py"),
                ORIGINAL, REWRITTEN, FINAL, "--concepts", CONCEPTS)
        self.assertIn("1-rewritten.txt                27/27 = 100%", r.stdout)
        self.assertIn("2-final.txt                    27/27 = 100%", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_english_example_keeps_every_concept_and_shows_its_added_figure(self):
        r = run(sys.executable, script("check.py"),
                ORIGINAL_EN, REWRITTEN_EN, FINAL_EN, "--concepts", CONCEPTS_EN)
        self.assertNotIn("LOST", r.stdout)
        # «global pandemic» became «COVID-19 pandemic»: a detail the original never gave
        self.assertIn("1-rewritten.txt: added 19", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout)
        r = run(sys.executable, script("check.py"), ORIGINAL, REWRITTEN, FINAL, "--concepts", CONCEPTS)
        self.assertIn("FIGURES: all 2 of the original are in every version, none added.", r.stdout)

    def test_detects_lost_concept_and_flipped_negation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.txt")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write(read(ORIGINAL).replace("Heidegger", "un filósofo")
                         .replace("principio de no contradicción", "principio de contradicción"))
            r = run(sys.executable, script("check.py"),
                    ORIGINAL, bad, "--concepts", CONCEPTS)
            self.assertEqual(r.returncode, 1)
            self.assertIn("LOST", r.stdout)
            self.assertIn("«no contradiccion»", r.stdout)

    def test_a_split_paragraph_fails_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig, split = os.path.join(tmp, "o.txt"), os.path.join(tmp, "s.txt")
            with open(orig, "w", encoding="utf-8") as fh:
                fh.write("The microgrid saves 5.7% of the cost. The supervisor is fast.\n")
            with open(split, "w", encoding="utf-8") as fh:
                fh.write("The microgrid saves 5.7% of the cost.\n\nThe supervisor is fast.\n")
            conc = os.path.join(tmp, "c.txt")
            with open(conc, "w", encoding="utf-8") as fh:
                fh.write("microgrid\n")
            r = run(sys.executable, script("check.py"), orig, split, "--concepts", conc)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("PARAGRAPHS: the original has 1", r.stdout)

    def test_a_minus_sign_is_part_of_the_figure(self):
        o = "The interval is -0.7 to +2.8, COVID-19 hit pages 5-7, and $-1.5$ or (−3) units."
        self.assertEqual(check.numbers_lost(o, o.replace("+2.8", "2.8")), [])  # «+» is no sign
        self.assertEqual(check.numbers_lost(o, o.replace("-0.7", "0.7")), ["-0.7"])
        self.assertEqual(check.numbers_added(o, o.replace("-0.7", "0.7")), ["0.7"])
        self.assertEqual(check.numbers_lost(o, o.replace("(−3)", "(-3)")), [])  # − is -
        self.assertEqual(check.numbers_lost(o, o.replace("$-1.5$", "$1.5$")), ["-1.5"])
        self.assertEqual(check.figures(o)[0]["19"], 1)  # COVID-19 has no negative 19
        self.assertEqual(check.figures(o)[0]["7"], 1)   # nor «5-7» a negative 7

    def test_concepts_match_across_hyphens_apostrophes_and_spelling(self):
        found = lambda term, text: bool(check.pattern(term).search(check.norm(text)))  # noqa: E731
        self.assertTrue(found("on-site microgrid", "an onsite microgrid"))
        self.assertTrue(found("on-site microgrid", "an on site microgrid"))
        self.assertTrue(found("realised-profit", "the realized profit"))
        self.assertTrue(found("optimiser's curse", "the optimizer’s curse"))
        self.assertTrue(found("modelling", "modeling"))
        self.assertFalse(found("modelling", "models"))
        self.assertFalse(found("realise", "reality"))
        self.assertFalse(found("ser", "servicio"))

    def test_check_reports_negations_the_version_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            o, v, c = (os.path.join(tmp, n) for n in ("o.txt", "v.txt", "c.txt"))
            with open(o, "w", encoding="utf-8") as fh:
                fh.write("Its first proposals, made after the incumbent was scored, use the microgrid.\n")
            with open(v, "w", encoding="utf-8") as fh:
                fh.write("Its first proposals, made without having seen the score, use the microgrid.\n")
            with open(c, "w", encoding="utf-8") as fh:
                fh.write("microgrid\n")
            r = run(sys.executable, script("check.py"), o, v, "--concepts", c)
            self.assertIn("NEGATIONS the version added", r.stdout)
            self.assertIn("without having", r.stdout)

    def test_a_count_in_words_the_original_never_gave_is_added(self):
        o = "Three optimisers search. On 30 trained agent teams, all three raise profit with six agents."
        self.assertEqual(check.numbers_added(o, o.replace("agent teams", "teams of three agents")), ["three"])
        self.assertEqual(check.numbers_added(o, o.replace("all three raise", "each raises")), [])
        self.assertEqual(check.numbers_added(o, o.replace("six agents", "6 agents")), [])
        self.assertEqual(check.numbers_added(o, "One of them, once a day: " + o), [])  # «one», «once»

    def test_acronym_definitions_are_found_and_required(self):
        o = ("We use a large language model (LLM, Claude) and a Markov Decision Process (MDP), "
             "see Fig. 2 (PDF) and Smith (2020).")
        self.assertEqual(check.definitions(o), [("large language model", "LLM"),
                                                ("Markov Decision Process", "MDP")])
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = (os.path.join(tmp, n) for n in ("o.txt", "v.txt", "c.txt"))
            with open(a, "w", encoding="utf-8") as fh:
                fh.write(o + "\n")
            with open(b, "w", encoding="utf-8") as fh:
                fh.write("An LLM (Claude) and a Markov Decision Process (MDP) are used, see "
                         "Fig. 2 (PDF) and Smith (2020).\n")
            with open(c, "w", encoding="utf-8") as fh:
                fh.write("LLM\n")
            r = run(sys.executable, script("check.py"), a, b, "--concepts", c)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("large language model (LLM)", r.stdout)

    def test_a_word_limit_fails_a_longer_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = (os.path.join(tmp, n) for n in ("o.txt", "v.txt", "c.txt"))
            with open(a, "w", encoding="utf-8") as fh:
                fh.write("The microgrid saves money every single day.\n")
            with open(b, "w", encoding="utf-8") as fh:
                fh.write("Every single day, the on-site microgrid saves the plant some money.\n")
            with open(c, "w", encoding="utf-8") as fh:
                fh.write("microgrid\n")
            r = run(sys.executable, script("check.py"), a, b, "--concepts", c)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("WORDS:", r.stdout)
            self.assertIn("11 (+4)", r.stdout)
            r = run(sys.executable, script("check.py"), a, b, "--concepts", c, "--word-limit", "10")
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("Over the limit of 10", r.stdout)

    def test_british_and_american_spelling_are_reported(self):
        o = "Optimization of the colour model and the modelling of the centre."
        v = "Optimisation of the color model and the modelling of the center."
        self.assertEqual(sorted(check.spelling_changes(o, v)),
                         [("centre", "center"), ("colour", "color"), ("optimization", "optimisation")])
        self.assertEqual(check.spelling_changes(o, o), [])
        self.assertEqual(check.spelling_changes("We rise early.", "We rize early."), [])  # no «rise»->«rize» pair in the original

    def test_check_counts_a_file_named_twice_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            f, conc = os.path.join(tmp, "a.txt"), os.path.join(tmp, "c.txt")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("The microgrid saves money.\n")
            with open(conc, "w", encoding="utf-8") as fh:
                fh.write("microgrid\n")
            r = run(sys.executable, script("check.py"), f, f, "--concepts", conc)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("1/1 = 100%", r.stdout)

    def test_negations_in_english(self):
        self.assertIn("not the", check.negations("This is not the answer."))
        self.assertIn("never again", check.negations("It will never again happen."))

    def test_ignores_accents_and_unicode_form(self):
        nfd_text = unicodedata.normalize("NFD", "La Crítica de la razón pura de Kant")
        self.assertTrue(check.pattern("critica de la razon pura").search(check.norm(nfd_text)))

    def test_whole_word_and_prefix(self):
        self.assertFalse(check.pattern("ser").search(check.norm("el servicio")))
        self.assertTrue(check.pattern("antinomia").search(check.norm("las antinomias")))
        self.assertTrue(check.pattern("subatómic*").search(check.norm("nivel subatómico")))

    def test_automatic_extraction(self):
        names = [n for n, _ in check.extract_concepts(read(ORIGINAL))]
        for expected in ("Aristóteles", "Tomás de Aquino", "Dasein"):
            self.assertIn(expected, names)
        self.assertNotIn("El", names)

    def test_list_flag_old_and_new(self):
        for flag in ("--list", "--listar"):
            r = run(sys.executable, script("check.py"), ORIGINAL, REWRITTEN, flag)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("concepts (automatic extraction)", r.stdout)

    def test_plurals_comments_and_figures(self):
        self.assertTrue(check.pattern("policy").search(check.norm("two policies")))
        self.assertTrue(check.pattern("luz").search(check.norm("las luces")))
        with tempfile.TemporaryDirectory() as tmp:
            conc = os.path.join(tmp, "c.txt")
            with open(conc, "w", encoding="utf-8") as fh:
                fh.write("C# | C sharp   # the language\n# a comment line\n")
            self.assertEqual(check.load_concepts(conc), [("C#", ["C#", "C sharp"])])
            a, b = os.path.join(tmp, "a.txt"), os.path.join(tmp, "b.txt")
            with open(a, "w", encoding="utf-8") as fh:
                fh.write("In 2020, 60% of the 1,990 staff moved home.\n")
            with open(b, "w", encoding="utf-8") as fh:
                fh.write("In 2020, sixty percent of the 1990 staff moved home.\n")
            r = run(sys.executable, script("check.py"), a, b, "--concepts", conc)
            self.assertIn("FIGURES that changed", r.stdout)
            self.assertIn("b.txt: lost 60\n", r.stdout)  # 1,990 = 1990, 2020 stays

    def test_a_lost_negation_is_not_hidden_by_the_same_pair_elsewhere(self):
        lost = check.negations("No es fácil. Pero no es imposible.") - check.negations(
            "No es fácil. Pero es imposible.")
        self.assertEqual(sorted(lost), ["no es"])
        self.assertEqual(sorted(check.negations("It doesn't apply.") - check.negations("It applies.")),
                         ["not apply"])
        self.assertFalse(check.negations("It doesn’t apply.") - check.negations("It does not apply."))

    def test_a_byte_order_mark_does_not_hide_the_first_concept(self):
        with tempfile.TemporaryDirectory() as tmp:
            conc, a = os.path.join(tmp, "c.txt"), os.path.join(tmp, "a.txt")
            with open(conc, "w", encoding="utf-8-sig") as fh:  # as Notepad saves it
                fh.write("Office\n")
            with open(a, "w", encoding="utf-8-sig") as fh:
                fh.write("Moreover, the Office opened.\n")
            r = run(sys.executable, script("check.py"), a, a, "--concepts", conc)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertNotIn("\ufeff", r.stdout)
            r = run(sys.executable, script("tells.py"), a)
            self.assertIn("stock opening", r.stdout)

    def test_figures_are_counted_compared_by_value_and_never_added(self):
        self.assertEqual(check.numbers_lost("In 2020 and again in 2020.", "In 2020."), ["2020"])
        self.assertEqual(check.numbers_lost("From 1.5 to 0.50.", "From 15 to 0.5."), ["1.5", "0.50"])
        self.assertEqual(check.numbers_lost("Hubo 1.990 votos, el 0,05.", "1990 votos; el 0.05."), [])
        self.assertEqual(check.numbers_lost("Siglo XX, Fase II.", "Siglo X, fase 2."), ["XX", "II"])
        self.assertEqual(check.numbers_lost("ML and CV methods.", "Learning methods."), [])
        self.assertEqual(check.numbers_added("Two or three days.", "2 or 3 days, 35% of staff."),
                         ["35"])
        self.assertEqual(check.numbers_added("Sixty percent agreed.", "60% agreed."), [])
        self.assertEqual(check.numbers_added("Dos o tres días.", "2 o 3 días."), [])

    def test_missing_file_exits_with_two(self):
        r = run(sys.executable, script("check.py"), ORIGINAL, "does-not-exist.txt")
        self.assertEqual(r.returncode, 2)


    def test_a_two_word_term_matches_the_orders_english_moves_it_into(self):
        """A real run lost 3 of 10 tries to «the cost of outages» and «microgrids on-site»."""
        for term, yes, no in (("outage cost*", ["outage costs", "the cost of outages", "cost of an outage"],
                               ["costs outage", "outage time"]),
                              ("on-site microgrid", ["onsite microgrids", "microgrids on-site",
                                                     "microgrids on site"], ["microgrids at the site"]),
                              ("Microsoft Teams", ["Microsoft Teams"], ["Teams of Microsoft"])):
            for t in yes:
                self.assertTrue(check.pattern(term).search(check.norm(t)), (term, t))
            for t in no:
                self.assertFalse(check.pattern(term).search(check.norm(t)), (term, t))

    def test_a_comparison_that_may_have_flipped(self):
        o = "Deep reinforcement learning controllers [2] outperform rule-based schedules in simulation."
        inverted = "Deep reinforcement learning controllers are out-performed by rule based scheduling [2]."
        self.assertEqual(check.comparison_changes(o, inverted), ["active «outperform» came back passive («… by»)"])
        self.assertEqual(check.comparison_changes(o, o.replace("outperform", "beat")), [])
        self.assertEqual(check.comparison_changes("A is superior to B.", "A is inferior to B."),
                         ["«superior» became «inferior»"])
        self.assertEqual(check.comparison_changes("B is outperformed by A.", "A outperforms B."),
                         ["passive «… by» came back active"])
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a.txt"), os.path.join(tmp, "b.txt")
            with open(a, "w", encoding="utf-8") as fh:
                fh.write(o + "\n")
            with open(b, "w", encoding="utf-8") as fh:
                fh.write(inverted + "\n")
            c = os.path.join(tmp, "concepts.txt")
            with open(c, "w", encoding="utf-8") as fh:
                fh.write("reinforcement learning\n")
            r = run(sys.executable, script("check.py"), a, b, "--concepts", c)
            self.assertIn("COMPARISONS that may have flipped", r.stdout)
            sheet = os.path.join(tmp, "sheet.md")
            run(sys.executable, script("review.py"), a, b, "-o", sheet)
            self.assertIn("FLAG: COMPARISON active «outperform» came back passive", read(sheet))


class Join(unittest.TestCase):
    def test_joins_with_y_and_respects_names(self):
        t = ("Goku entrena todos los días. La serie lo muestra sin prisa. "
             "Vegeta lo observa de lejos. Pero nunca lo admite.\n")
        concepts = [("Goku", ["Goku"]), ("Vegeta", ["Vegeta"])]
        self.assertEqual(join.join_text(t, concepts).strip(),
                         "Goku entrena todos los días y la serie lo muestra sin prisa "
                         "y Vegeta lo observa de lejos, pero nunca lo admite.")

    def test_flags_names_missing_from_concepts(self):
        doubtful = []
        r = join.join_text("Goku entrena. Vegeta lo observa.\n", doubtful=doubtful)
        self.assertIn("y vegeta", r)
        self.assertEqual(doubtful, ["Vegeta"])

    def test_changes_no_other_word(self):
        text = read(ORIGINAL)
        r = join.join_text(text, check.load_concepts(CONCEPTS))
        outside = ("y", "pero", "sin", "embargo", "asimismo", "además")
        words = lambda t: [w.lower() for w in re.findall(r"\w+", t) if w.lower() not in outside]  # noqa: E731
        self.assertEqual(words(r), words(text))
        self.assertLess(r.count(". "), text.count(". "))

    def test_common_words_are_not_proper_nouns(self):
        concepts = [("San Cristóbal de Las Casas", ["San Cristóbal de Las Casas"])]
        proper = join.proper_nouns("Llegamos a San Cristóbal de Las Casas.", concepts)
        self.assertIn("Cristóbal", proper)
        self.assertNotIn("Las", proper)

    def test_respects_paragraphs_and_titles(self):
        r = join.join_text("Un título\n\nUno dos. Tres cuatro.\n\nCinco seis. Siete ocho.\n")
        self.assertEqual(r, "Un título\n\nUno dos y tres cuatro.\n\nCinco seis y siete ocho.\n")

    def test_english_joins_with_and_and_respects_names(self):
        t = ("Dr. Smith moved to Boston. The city was cold. However, he stayed. "
             "I liked it. Moreover, the food was great. But winter came.\n")
        self.assertEqual(join.detect_language(t), "en")
        self.assertEqual(join.join_text(t).strip(),
                         "Dr. Smith moved to Boston and the city was cold, but he stayed "
                         "and I liked it and the food was great, but winter came.")

    def test_pauses_leave_a_few_periods_and_keep_connectors(self):
        par = ("El ser es. El no-ser no es. Nada nace de la nada. Sin embargo, todo cambia. "
               "La semilla crece. El árbol da fruto. Segundo, el fuego calienta. El agua hierve.")
        out = join.join_text(par, pauses=2, lang="es")
        self.assertEqual(len(re.findall(r"\.(?:\s|$)", out)), 3, out)
        self.assertIn("Segundo, el fuego calienta", out)  # cut where the idea changes
        self.assertNotIn(" y sin embargo", out)
        self.assertNotIn(" y segundo", out)
        self.assertEqual(join.join_text(par, lang="es"), join.join_text(par, pauses=None, lang="es"))
        for p in join.join_text(par, pauses=2, lang="es").split(". "):
            self.assertGreater(len(re.findall(r"\w+", p)), 6, p)  # no sentence left alone

    def test_pauses_join_pero_without_a_double_connector(self):
        par = ("El ser es y no cambia nunca. El no-ser no es ni se piensa. Pero Heráclito "
               "dijo lo contrario. Todo fluye para él. Nada permanece igual. El río cambia.")
        for seed in (7, 11, 23):
            out = join.join_text(par, pauses=1, seed=seed, lang="es")
            self.assertNotIn("y pero", out)
            self.assertTrue(", pero Heráclito" in out or ". Pero Heráclito" in out, out)

    def test_english_keeps_acronyms_and_initials(self):
        t = ("AI tools spread fast. COVID-19 changed work. They met John F. Kennedy there. "
             "Then he left.\n")
        self.assertEqual(join.join_text(t, lang="en").strip(),
                         "AI tools spread fast and COVID-19 changed work and they met "
                         "John F. Kennedy there and then he left.")
        out = join.join_text(t, pauses=1, lang="en")
        self.assertNotIn("aI", out)
        self.assertNotIn("cOVID", out)
        self.assertIn("John F. Kennedy", out)

    def test_a_long_paragraph_keeps_more_periods_with_words_per_period(self):
        sentences = [f"The plant number {i} runs a shift of {i + 2} hours and the agents follow it."
                     for i in range(1, 13)]
        para = " ".join(sentences) + "\n"
        plain = join.join_text(para, pauses=2, lang="en")
        scaled = join.join_text(para, pauses=2, lang="en", words_per_period=40)
        periods = lambda t: len(re.findall(r"\.(?:\s|$)", t))  # noqa: E731
        self.assertLessEqual(periods(plain), 3)
        self.assertGreater(periods(scaled), periods(plain))
        self.assertEqual(join.join_text("Short one. Two here. Three now. Four too.\n", pauses=2,
                                        lang="en", words_per_period=40),
                         join.join_text("Short one. Two here. Three now. Four too.\n", pauses=2, lang="en"))

    def test_english_drops_filler_openers(self):
        par = ("Remote work grew fast in 2020. Many firms kept it after the crisis. Moreover, "
               "commuting time went down for most staff. Workers liked the change a lot. "
               "Furthermore, offices emptied in big cities. Rents fell in many downtown areas.")
        for pauses in (None, 1, 2):
            out = join.join_text(par, pauses=pauses, lang="en")
            self.assertNotIn("oreover", out)
            self.assertNotIn("urthermore", out)
            self.assertNotIn("and also", out)
            self.assertIn("ommuting time went down", out)
        self.assertIn("and iPhone sales", join.join_text("Prices fell. Moreover, iPhone sales grew.",
                                                         lang="en"))
        self.assertIn("modern art and museums", join.join_text("We saw modern art. Museums "
                                                               "were full.", lang="en"))
        # Spanish keeps «Además»: it is ordinary there and was measured that way
        es = "El turismo crece. Además, la sierra atrae visitantes."
        self.assertEqual(join.join_text(es, lang="es").strip(),
                         "El turismo crece y además la sierra atrae visitantes.")

    def test_pauses_join_and_without_a_double_connector(self):
        par = ("The plan was simple and clear to all. It worked for a year or so. And then "
               "the money ran out for good. Nobody saw it coming at all. The team moved on. "
               "Most found new jobs.")
        for seed in (7, 11, 23):
            out = join.join_text(par, pauses=1, seed=seed, lang="en")
            self.assertNotIn("and and", out.lower())
            self.assertNotIn("; and then", out)

    def test_no_dashes_turns_dashes_into_commas(self):
        t = ("The new policy — announced without warning — affects thousands of workers. "
             "The changes -- long overdue -- start in 1990–2000 terms.\n")
        out = join.join_text(t, lang="en", no_dashes=True)
        self.assertIn("The new policy, announced without warning, affects", out)
        self.assertIn("the changes, long overdue, start in 1990–2000 terms", out)
        dialogue = "—Hola —dijo ella—, ¿vienes?"
        self.assertEqual(join.replace_dashes(dialogue), dialogue)  # dialogue is left alone
        self.assertIn(" — ", join.join_text(t, lang="en"))  # off by default
        self.assertEqual(join.replace_dashes("It is free—on every plan—."), "It is free, on every plan.")
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(t)
            r = run(sys.executable, script("join.py"), src, "-o", out, "--no-dashes")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn(" — ", read(out))

    def test_a_joined_question_is_lowercased_after_the_mark(self):
        self.assertEqual(join.join_text("Llegó tarde. ¿Vienes mañana?", lang="es").strip(),
                         "Llegó tarde y ¿vienes mañana?")
        self.assertIn("y ¿Juan viene", join.join_text("Llegó tarde. ¿Juan viene?",
                                                      [("Juan", ["Juan"])], lang="es"))

    def test_markdown_blocks_are_left_alone_and_list_items_joined_one_by_one(self):
        doc = ("# A Title. With a period\n\n```\nx = 1. Y = 2.\n```\n\n"
               "- First item. It has two sentences.\n- Second item. Also two.\n\n"
               "| a. B | c. D |\n\nPlain text. More text.\n")
        out = join.join_text(doc, lang="en")
        self.assertIn("# A Title. With a period", out)
        self.assertIn("```\nx = 1. Y = 2.\n```", out)
        self.assertIn("- First item and it has two sentences.\n- Second item and also two.", out)
        self.assertIn("| a. B | c. D |", out)
        self.assertIn("Plain text and more text.", out)

    def test_initials_dotted_abbreviations_and_numbered_steps_are_not_sentence_ends(self):
        cases = [
            ("The Hobbit was written by J.R.R. Tolkien. It was a hit.", "en",
             "The Hobbit was written by J.R.R. Tolkien and it was a hit."),
            ("She lives in Washington, D.C. The city is big.", "en",
             "She lives in Washington, D.C. The city is big."),
            ("The march was led by Rev. Martin Luther King. It was huge.", "en",
             "The march was led by Rev. Martin Luther King and it was huge."),
            ("We met at 9 a.m. Everyone came.", "en", "We met at 9 a.m. Everyone came."),
            ("Viajó a EE.UU. Allí vivió.", "es", "Viajó a EE.UU. Allí vivió."),
            ("Lo dice en el libro I, cap. VI de su obra. Es claro.", "es",
             "Lo dice en el libro I, cap. VI de su obra y es claro."),
            ("1. Open the box. 2. Remove the tray. 3. Close it.", "en",
             "1. Open the box. 2. Remove the tray. 3. Close it."),
        ]
        for text, lang, expected in cases:
            for pauses in (None, 1):
                out = join.join_text(text, lang=lang, pauses=pauses).strip()
                if pauses is None:
                    self.assertEqual(out, expected)
                self.assertNotRegex(out, r"(?:J\.R\.R|D\.C|Rev|a\.m|EE\.UU|cap) (?:and|y) ")

    def test_names_with_a_possessive_or_a_curly_apostrophe_keep_their_capital(self):
        self.assertIn("and Microsoft's survey", join.join_text(
            "Sales grew fast. Microsoft's survey said so.", [("Microsoft", ["Microsoft"])], lang="en"))
        self.assertIn("and I’m tired", join.join_text("It was late. I’m tired.", lang="en"))
        self.assertIn("and O'Brien came", join.join_text("It was late. O'Brien came.", lang="en"))

    def test_lowercased_names_ending_like_verbs_are_still_reported(self):
        doubtful = []
        join.join_text("The trip was long. Italy was nice. Boeing built it.", doubtful=doubtful,
                       lang="en")
        self.assertEqual(doubtful, ["Boeing", "Italy"])
        doubtful = []
        join.join_text("Javier estaba cansado. Pilar no vino.", doubtful=doubtful, lang="es")
        self.assertEqual(doubtful, ["Pilar"])

    def test_no_dashes_leaves_ranges_and_line_dashes(self):
        self.assertEqual(join.replace_dashes("It ran in 1990—2000 and from 1939 – 1945 — mostly."),
                         "It ran in 1990—2000 and from 1939 – 1945, mostly.")
        self.assertEqual(join.replace_dashes("Pros:\n— fast\n— cheap"), "Pros:\n— fast\n— cheap")
        self.assertEqual(join.replace_dashes("Pros: — fast"), "Pros: fast")

    def test_joining_never_changes_a_figure(self):
        texts = [read(f) for f in (ORIGINAL, REWRITTEN, ORIGINAL_EN, REWRITTEN_EN)]
        texts.append("Accuracy was 0.50 in 2020. It rose to 0.75 by 2021. The 3 models used "
                     "1,200 samples. Step 2. Then 3.5% more. Fig. 4 shows it. In 1990–2000 "
                     "the rate was 7. The rest was 12.")
        for t in texts:
            for kw in ({}, {"pauses": 2}, {"no_dashes": True}, {"pauses": 1, "no_dashes": True}):
                out = join.join_text(t, **kw)
                self.assertEqual(check.figures(out)[0], check.figures(t)[0], kw)

    def test_detects_the_language(self):
        self.assertEqual(join.detect_language(read(ORIGINAL)), "es")
        self.assertEqual(join.detect_language(read(ORIGINAL_EN)), "en")
        self.assertEqual(join.detect_language("The cat sat on the mat and it was happy."), "en")

    def test_spanish_example_final_is_reproducible(self):
        r = join.join_text(read(REWRITTEN), check.load_concepts(CONCEPTS))
        self.assertEqual(r, read(FINAL))

    def test_english_example_final_is_reproducible(self):
        r = join.join_text(read(REWRITTEN_EN), check.load_concepts(CONCEPTS_EN))
        self.assertEqual(r, read(FINAL_EN))

    def test_cli_english_and_old_flags_give_the_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, old = os.path.join(tmp, "new.txt"), os.path.join(tmp, "old.txt")
            r1 = run(sys.executable, script("join.py"), REWRITTEN_EN, "-o", new,
                     "--concepts", CONCEPTS_EN, "--lang", "en", "--ratio", "1.0",
                     "--max-words", "400")
            r2 = run(sys.executable, script("join.py"), REWRITTEN_EN, "--salida", old,
                     "--conceptos", CONCEPTS_EN, "--idioma", "en", "--proporcion", "1.0",
                     "--maximo", "400")
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertEqual(read(new), read(FINAL_EN))
            self.assertEqual(read(old), read(FINAL_EN))


class Rewrite(unittest.TestCase):
    def test_prompt_with_spanish_lead(self):
        prompt, lead = rewrite.build_prompt("El turismo en la sierra crece.")
        self.assertEqual(lead, "El turismo")
        self.assertTrue(prompt.startswith("<source_text>\n"))
        self.assertTrue(prompt.endswith("<target_text>\nEl turismo"))

    def test_cleans_the_output(self):
        self.assertEqual(rewrite.clean_output("El turismo", " de la sierra  crece.\n</target_text>junk"),
                         "El turismo de la sierra crece.")

    def test_restores_the_percent_sign(self):
        self.assertEqual(rewrite.restore_percent_signs("Arabica es el 60% del total.",
                                                       "Arabica representa el 60 del total."),
                         "Arabica representa el 60% del total.")
        self.assertEqual(rewrite.restore_percent_signs("Sube 5% al año.", "Sube 5% cada año."),
                         "Sube 5% cada año.")
        self.assertEqual(rewrite.restore_percent_signs("Hay 60 países.", "Son 60 países."),
                         "Son 60 países.")

    def test_copied_share(self):
        p = ("Aristóteles sostiene que el acto tiene primacía sobre la potencia en varios "
             "sentidos y que la potencia de hablar se comprende cuando se ejerce el habla.")
        self.assertEqual(rewrite.copied_share(p, p), 1.0)
        half = ("Para Aristóteles el acto va antes que la potencia, y la potencia de hablar "
                "se comprende cuando se ejerce el habla.")
        self.assertLess(rewrite.copied_share(p, half), 0.6)
        # a shared name or phrase shorter than 8 words does not count as copied
        self.assertEqual(rewrite.copied_share("Parménides de Elea negó el cambio.",
                                              "Según Parménides de Elea, nada cambia."), 0.0)

    def test_retries_a_copied_try_and_names_the_lost_concept(self):
        """The fake llama copies the paragraph on the first try and rewrites it on the
        second; a paragraph that always loses «encina» stays as the original and the
        warning says which concept it lost."""
        text = ("Una bellota tiene la potencia de convertirse en una encina, pero una piedra "
                "no tiene esa potencia y nunca va a llegar a ser un árbol de ninguna clase.\n\n"
                "Cuando la encina adulta está en acto respecto de las capacidades que tenía cuando "
                "era bellota y por eso decimos que la potencia se ha actualizado del todo.\n")
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            fake = os.path.join(tmp, "fake_llama.py")
            calls = os.path.join(tmp, "calls")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write(
                    "import os, sys\n"
                    "args = sys.argv[1:]\n"
                    "prompt = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
                    "src = prompt.split('<source_text>\\n')[1].split('\\n</source_text>')[0]\n"
                    f"c = {calls!r}\n"
                    "n = int(open(c).read()) + 1 if os.path.exists(c) else 1\n"
                    "open(c, 'w').write(str(n))\n"
                    "if src.startswith('Cuando la'):\n"
                    "    out = ' planta se vuelve adulta, la potencia queda actualizada por completo'\n"
                    "    out += ' desde que era una bellota pequeña en el suelo del bosque.'\n"
                    "elif n == 1:\n"
                    "    out = ' ' + ' '.join(src.split()[2:])\n"
                    "else:\n"
                    "    out = (' puede llegar a ser encina; la piedra, en cambio, no tiene'\n"
                    "           ' esa potencia ni se hará árbol jamás, por más tiempo que pase.')\n"
                    "sys.stdout.buffer.write((out + '\\n</target_text>').encode('utf-8'))\n")
            src, out, conc = (os.path.join(tmp, n) for n in ("in.txt", "out.txt", "c.txt"))
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(conc, "w", encoding="utf-8") as fh:
                fh.write("encina\nbellota\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--concepts", conc,
                    "--tries", "3", "--threads", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            first, second = read(out).strip().split("\n\n")
            self.assertTrue(first.startswith("Una bellota puede llegar a ser encina"), first)
            self.assertIn("Paragraph 1 of 2: done, try 2", r.stdout)
            self.assertEqual(second, text.strip().split("\n\n")[1])
            self.assertIn("2 (encina)", r.stdout)

    def test_keeps_the_least_copied_try_when_all_copy(self):
        text = ("Año tras año, el pingüino «Nuño» camina sin prisa hacia el sur por la costa "
                "helada, siempre por el mismo camino que conoce desde que era muy pequeño.\n")
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_llama(tmp)
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out,
                    "--tries", "2", "--threads", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("copied long stretches", r.stdout)
            self.assertIn("1 (100%)", r.stdout)

    def test_only_redoes_the_listed_paragraphs_and_keeps_the_rest(self):
        text = ("Año tras año, el pingüino «Nuño» camina sin prisa hacia el sur.\n\n"
                "El mar helado cruje bajo sus patas cada mañana de invierno.\n")
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_llama(tmp)
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("Primero, ya corregido a mano.\n\nSegundo, ya corregido a mano.\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--only", "2",
                    "--tries", "1", "--threads", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            first, second = read(out).strip().split("\n\n")
            self.assertEqual(first, "Primero, ya corregido a mano.")
            self.assertEqual(second, text.strip().split("\n\n")[1])
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("Solo un párrafo.\n")
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--only", "2", env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("same count", r.stderr)

    def test_a_long_paragraph_is_split_in_whole_sentences(self):
        p = ("We propose a supervisor for six agents. It was tested by Smith et al. on four days "
             "with care. Profit rose by 5.7% at the smallest budget of all. The gains were "
             "smaller than predicted. Neither superiority nor equivalence was found here.")
        runs = rewrite.parts(p, "text", 20)
        self.assertGreater(len(runs), 1)
        self.assertEqual(" ".join(runs), p)
        self.assertTrue(all(len(r.split()) <= 20 for r in runs))
        self.assertIn("Smith et al. on four days", " ".join(r for r in runs if "Smith" in r))
        self.assertEqual(rewrite.parts(p, "text", 0), [p])     # off by default
        self.assertEqual(rewrite.parts(p, "text", 500), [p])   # short enough
        tex = ("We follow \\citet{a. B} closely. The cost is $x. Y$ per unit in every case we "
               "ran. It drops by 5\\% overall. The rest stays the same as before.")
        runs = rewrite.parts(tex, "latex", 10)
        self.assertGreater(len(runs), 1)
        self.assertTrue(any("\\citet{a. B} closely." in r for r in runs))
        self.assertTrue(any("$x. Y$" in r for r in runs))
        self.assertEqual(rewrite.parts("A comment % here.\nThen more words go on.", "latex", 2),
                         ["A comment % here.\nThen more words go on."])

    def test_max_words_keeps_one_paragraph(self):
        text = ("Agents run every hour on the line. A supervisor picks a directive for them. "
                "Three methods search the same space. The language model reads the history "
                "first. Gains were smaller than predicted.\n")
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            log = os.path.join(tmp, "calls.txt")
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\n"
                         f"open({log!r}, 'a').write('x')\n"
                         "sys.stdout.write(' then went on with other words in its own way.\\n</target_text>')\n")
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "1",
                    "--max-words", "12", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("one paragraph in", r.stdout)
            result = read(out).strip()
            self.assertNotIn("\n", result)
            self.assertGreater(len(read(log)), 1)  # one call per part

    def test_a_try_that_adds_markup_is_a_soft_problem(self):
        o = "Profit rose by 5.7% at the smallest budget, and the agents kept learning every day."
        r = "At the smallest budget profit went up by $5.7%$, while the agents went on learning daily."
        self.assertEqual(rewrite.symbols_added(o, r), ["$"])
        self.assertEqual(rewrite.acceptable(o, r, set(), [], 0.9)[0], "(symbols added)")
        self.assertIn("(symbols added)", rewrite.SOFT)  # kept if every try has it, and reported
        self.assertEqual(rewrite.symbols_added("Costs $5 a day.", "A day costs $5."), [])

    def test_a_long_paragraph_that_fails_is_redone_in_parts(self):
        sentences = ["The supervisor picks a directive for the microgrid every hour."] + [
            f"Sentence number {w} talks about the agents and the line and the energy cost here."
            for w in ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                      "ten", "eleven", "twelve")]
        text = " ".join(sentences) + "\n"
        self.assertGreater(len(text.split()), rewrite.AUTO_PARTS)
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            fake = os.path.join(tmp, "fake.py")
            # It drops «microgrid» whenever the source is long, like the real model did.
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\nargs = sys.argv[1:]\n"
                         "prompt = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
                         "src = prompt.split('<source_text>\\n')[1].split('\\n</source_text>')[0]\n"
                         "words = src.split()[2:]\n"
                         "out = ' '.join(w for w in words if len(src.split()) < 120 or w != 'microgrid')\n"
                         "out = out.replace('talks about', 'is about').replace('every hour', 'each hour')\n"
                         "sys.stdout.write(' ' + out + '\\n</target_text>')\n")
            src, out, conc = (os.path.join(tmp, n) for n in ("in.txt", "out.txt", "c.txt"))
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(conc, "w", encoding="utf-8") as fh:
                fh.write("microgrid\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--concepts", conc,
                    "--tries", "1", "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("rewriting it in", r.stdout)
            result = read(out).strip()
            self.assertNotIn("\n", result)       # still one paragraph
            self.assertIn("microgrid", result)    # and the term is back
            self.assertIn("is about", result)     # rewritten, not the original
            self.assertIn("paragraph 1, part 2:", r.stdout)
            # Redo only part 2: a hand fix in part 1 survives, part 2 is regenerated.
            fixed = result.replace("each hour", "every single hour", 1)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(fixed + "\n")
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--concepts", conc,
                    "--only", "1", "--part", "2", "--tries", "1", "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("part 2 of", r.stdout)
            self.assertIn("every single hour", read(out))
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--only", "1",
                    "--part", "9", env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("has parts 1 to", r.stderr)
            # Candidates for part 2 alone: whole paragraphs, measured in context, then --take.
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--concepts", conc,
                    "--only", "1", "--part", "2", "--candidates", "2", "--tries", "1",
                    "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            cands = sorted(f for f in os.listdir(out + ".candidates") if f.startswith("p01-part2-")
                           and f.endswith(".txt"))
            self.assertEqual(len(cands), 2, r.stdout)
            first = read(os.path.join(out + ".candidates", cands[0])).strip()
            self.assertIn("every single hour", first)   # the other parts, hand fix included
            self.assertNotIn("\n", first)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out,
                    "--take", "1=" + os.path.join(out + ".candidates", cands[0]), env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--concepts", conc,
                    "--only", "1", "--part", "2", "--tries", "1", "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # the record followed --take
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--concepts", conc,
                    "--only", "1", "--candidates", "2", "--tries", "1", "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            folder = out + ".candidates"
            found = sorted(f for f in os.listdir(folder) if re.fullmatch(r"p01-\d+\.txt", f))
            self.assertEqual(len(found), 2, r.stdout)  # whole-paragraph tries all lose «microgrid»
            for f in found:
                c = read(os.path.join(folder, f)).strip()
                self.assertIn("microgrid", c)
                self.assertNotIn("\n", c)

    def test_a_try_identical_to_the_original_is_named_in_the_report(self):
        report = {"untouched": [], "copied": [], "tells": [], "numbers": [], "symbols": []}
        rewrite.note(report, "1 (part 3)", "Same text.", "Same text.", None,
                     rewrite.collections.Counter(), "en")
        self.assertEqual(report["untouched"], ["1 (part 3) (the model gave it back unchanged)"])

    def test_a_latex_percent_in_plain_text_is_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\n"
                         "sys.stdout.write(' went up by 5.7-6.7\\\\% at the budget of three in the plant.\\n</target_text>')\n")
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("Daily profit rose by 5.7–6.7% at the smallest budget of three.\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "1",
                    "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("5.7-6.7% at", read(out))
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\n"
                         "sys.stdout.write(' went up by 5.7–6.7% at $B=3$ in the plant, the smallest budget.\\n</target_text>')\n")
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "1",
                    "--max-copied", "1", env=env)
            self.assertIn("at B=3 in", read(out))
            self.assertNotIn("$", read(out))
            self.assertNotIn("\\", read(out))

    def test_terms_of_art_can_be_locked_for_the_model(self):
        concepts = check.load_concepts_from_lines(["cross-entropy method", "frozen", "directive*",
                                                   "large language model | LLM"]) \
            if hasattr(check, "load_concepts_from_lines") else None
        if concepts is None:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
                fh.write("cross-entropy method\nfrozen\ndirective*\nlarge language model | LLM\non-site\n")
            self.addCleanup(os.remove, fh.name)
            concepts = check.load_concepts(fh.name)
        text = ("Frozen agents use a cross-entropy method and a large language model (LLM) to pick "
                "directives on-site, see [1].")
        masked, terms = rewrite.protect_terms(text, concepts)
        self.assertIn("a [2] and a [3]", masked)               # numbered after the existing [1]
        self.assertIn("Frozen agents", masked)                  # one plain word stays readable
        self.assertIn("pick directives", masked)
        self.assertEqual(sorted(terms.values()), ["cross-entropy method", "large language model", "on-site"])
        self.assertEqual(rewrite.restore_terms(masked, terms), text)
        self.assertIsNone(rewrite.restore_terms(masked.replace("[3]", ""), terms))

    def test_protect_terms_reaches_the_model_and_comes_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            log = os.path.join(tmp, "prompt.txt")
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\nargs = sys.argv[1:]\n"
                         "p = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
                         f"open({log!r}, 'w', encoding='utf-8').write(p)\n"
                         "sys.stdout.write(' now sets [1] against [2] on the line.\\n</target_text>')\n")
            src, out, conc = (os.path.join(tmp, n) for n in ("in.txt", "out.txt", "c.txt"))
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("This paper compares the cross-entropy method with random search on the line.\n")
            with open(conc, "w", encoding="utf-8") as fh:
                fh.write("cross-entropy method\nrandom search\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--concepts", conc,
                    "--protect-terms", "--tries", "1", "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("the [1] with [2]", read(log))
            self.assertIn("This paper now sets cross-entropy method against random search", read(out))

    def test_a_long_paragraph_gets_two_whole_tries_before_parts(self):
        text = " ".join(f"Sentence {w} says the microgrid line runs and the agents follow the plan here."
                        for w in ("one", "two", "three", "four", "five", "six", "seven", "eight",
                                  "nine", "ten", "eleven", "twelve", "thirteen")) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            calls = os.path.join(tmp, "calls")
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import os, sys\nargs = sys.argv[1:]\n"
                         f"open({calls!r}, 'a').write('x')\n"
                         "p = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
                         "src = p.split('<source_text>\\n')[1].split('\\n</source_text>')[0]\n"
                         "out = ' '.join(src.split()[2:]).replace('runs and', 'works while')\n"
                         "if len(src.split()) > 120: out = out.replace('microgrid ', '')\n"
                         "sys.stdout.write(' ' + out + '\\n</target_text>')\n")
            src, out, conc = (os.path.join(tmp, n) for n in ("in.txt", "out.txt", "c.txt"))
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(conc, "w", encoding="utf-8") as fh:
                fh.write("microgrid\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--concepts", conc,
                    "--tries", "6", "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            parts = int(re.search(r"rewriting it in (\d+) parts", r.stdout).group(1))
            self.assertIn("left as the original in 2 tries", r.stdout)
            self.assertEqual(len(read(calls)), 2 + parts)

    def test_resume_redoes_only_what_is_still_the_original(self):
        text = ("The first paragraph talks about the plant and its energy use today.\n\n"
                "The second paragraph talks about the agents and the supervisor here.\n")
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._echo_llama(tmp)
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(out, "w", encoding="utf-8") as fh:  # stopped after paragraph 1
                fh.write("Already rewritten by hand, kept.\n\n" + text.split("\n\n")[1])
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--resume",
                    "--tries", "1", "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("1 paragraphs kept, 1 to do", r.stdout)
            first, second = read(out).strip().split("\n\n")
            self.assertEqual(first, "Already rewritten by hand, kept.")
            self.assertNotEqual(second, text.split("\n\n")[1].strip())

    def test_citations_and_formulas_are_placeholders_in_text(self):
        t = ("Outage costs fall (Smith et al., 2020; Lee & Park, 2019). Controllers [12], [14]–[16] "
             "and [^3] win, though Wang (2021) and Kim (2020, p. 4) disagree; we use $r_t = p_t q_t$ "
             "and \\(\\gamma\\), at costs of $5 and $10 (95% CI −0.7 to +2.8) (LLM, Claude) in 2020.")
        shown, pieces = rewrite.protect_citations(t)
        # a numbered cluster is one piece (alone, its «–» came back as «--»); a narrative
        # citation stays words (locked, it came back as «… are noisy [3]»)
        self.assertEqual(list(pieces.values()), ["(Smith et al., 2020; Lee & Park, 2019)",
                                                 "[12], [14]–[16]", "[^3]", "$r_t = p_t q_t$",
                                                 "\\(\\gamma\\)"])
        self.assertIn("though Wang (2021) and Kim (2020, p. 4) disagree", shown)
        self.assertIn("costs of $5 and $10 (95% CI −0.7 to +2.8) (LLM, Claude) in 2020.", shown)
        self.assertEqual(rewrite.restore_terms(shown, pieces), t)

    def test_the_authors_of_a_narrative_citation_are_concepts(self):
        t = ("Wang (2021) and Kim (2020, p. 4) disagree. Recently, Álvarez y Núñez (2019) and "
             "Smith et al. (2018) did not, nor did O’Brien’s (2017) model (Lee, 2016).")
        self.assertEqual(check.cited_authors(t), [
            ("Wang (2021)", "Wang"), ("Kim (2020, p. 4)", "Kim"),
            ("Álvarez y Núñez (2019)", "Álvarez"), ("Álvarez y Núñez (2019)", "Núñez"),
            ("Smith et al. (2018)", "Smith"), ("O’Brien’s (2017)", "O’Brien")])
        concepts = check.with_definitions([("Kim", ["Kim"])], t)  # a concept already: not twice
        self.assertEqual([c for c, _ in concepts].count("Kim (2020, p. 4)"), 0)
        self.assertIn(("Wang (2021)", ["Wang"]), concepts)
        lost = rewrite.concepts_in(t, concepts) - rewrite.concepts_in(t.replace("Wang ", ""), concepts)
        self.assertEqual(lost, {"Wang (2021)"})

    def test_brackets_the_model_swapped_are_put_back(self):
        """A real try wrote «(1)»… «(4)» for the placeholders, others «Wang [2021]»."""
        shown = ("Costs fall [1]. Controllers [2] win, though Wang (2021) and Kim (2020, p. 4) "
                 "disagree; a list (3) stays.")
        self.assertEqual(rewrite.repair_brackets(shown, "Costs fall (1). Controllers (2) win; Wang [2021] "
                                                        "and Kim [2020, p.4] disagree, a list (3) stays."),
                         "Costs fall [1]. Controllers [2] win; Wang (2021) and Kim (2020, p. 4) disagree, "
                         "a list (3) stays.")
        self.assertEqual(rewrite.repair_brackets(shown, "Costs fall [1], [2] win; Wang [2022] says."),
                         "Costs fall [1], [2] win; Wang [2022] says.")  # another year is not repaired

    def test_citations_out_of_order_come_back_in_place(self):
        """«[2] … [1]» become pieces 1 and 2: putting them back one after the other swapped them."""
        t = "As [2] showed, and [1] before it, costs fall."
        shown, pieces = rewrite.protect_citations(t)
        self.assertEqual(shown, "As [1] showed, and [2] before it, costs fall.")
        self.assertEqual(rewrite.restore_terms(shown, pieces), t)
        self.assertEqual(rewrite.restore_terms("Costs fall, as [1] showed and [2] before it.", pieces),
                         "Costs fall, as [2] showed and [1] before it.")

    def test_a_try_that_loses_a_citation_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            calls, fake = os.path.join(tmp, "calls"), os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import os, sys\n"
                         f"c = {calls!r}\n"
                         "n = int(open(c).read()) + 1 if os.path.exists(c) else 1\n"
                         "open(c, 'w').write(str(n))\n"
                         "out = ' gains in the plant shrink under [1], as Wang (2021) found.' if n == 1 else "
                         "' gains in the plant shrink under [1], as Wang (2021) found with [2].'\n"
                         "sys.stdout.write(out + '\\n</target_text>')\n")
            src, out = os.path.join(tmp, "in.md"), os.path.join(tmp, "out.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("The reported gains shrink under $r_t = p_t$, as Wang (2021) found with [12].\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "2",
                    "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("done, try 2", r.stdout)  # try 1 lost «[12]»
            self.assertIn("shrink under $r_t = p_t$, as Wang (2021) found with [12].", read(out))

    def test_lead_replaces_the_opening_words(self):
        prompt, lead = rewrite.build_prompt("Uno de los problemas más importantes.", lead="Desde la")
        self.assertEqual(lead, "Desde la")
        self.assertTrue(prompt.endswith("<target_text>\nDesde la"))
        self.assertEqual(rewrite.build_prompt("Uno de los problemas.")[1], "Uno de")

    def test_citation_problem(self):
        o = ('Aristóteles: "aquello que está en potencia no puede actualizarse por sí mismo" '
             '(Física, III, 1). La bellota (el fruto de la encina).')
        ok = ('Escribe: "aquello que está en potencia no puede actualizarse por sí mismo" '
              '(Física, III, 1). La bellota (fruto de la encina).')
        self.assertIsNone(rewrite.citation_problem(o, ok))
        self.assertEqual(rewrite.citation_problem(o, ok.replace("aquello que", "la que")),
                         "(quote changed)")
        self.assertEqual(rewrite.citation_problem(o, ok.replace("(Física, III, 1)",
                                                                "(De Anima, libro i, cap. vi)")),
                         "(invented reference)")

    def test_english_lead_skips_a_filler_opener(self):
        self.assertEqual(rewrite.build_prompt("Moreover, the food was great today.", lang="en")[1],
                         "The food")
        self.assertEqual(rewrite.build_prompt("Moreover, the food was great.")[1], "Moreover, the")
        self.assertEqual(rewrite.build_prompt("Además, el turismo crece.", lang="es")[1],
                         "Además, el")

    def test_context_grows_with_long_paragraphs(self):
        self.assertEqual(rewrite.context_size("una dos tres", 109), 4096)
        long = " ".join(["palabra"] * 1500)
        n = 1500 * 3 + 100
        self.assertGreaterEqual(rewrite.context_size(long, n), 2 * 1500 + n)
        self.assertEqual(rewrite.context_size(long, n) % 1024, 0)

    def test_words_made_of_roman_letters_are_not_references(self):
        o = "La ley cambió el derecho en el siglo XX."
        for r in ("La ley (civil) cambió el derecho en el siglo XX.",
                  "The law (I think) changed it in the XX century.",
                  "Una mezcla (mix) de leyes cambió el derecho en el siglo XX."):
            self.assertIsNone(rewrite.citation_problem(o, r), r)
        for r in ("La ley cambió el derecho (De Anima, libro i, cap. vi).",
                  "La ley cambió el derecho (vol. XII).", "La ley cambió (2019)."):
            self.assertEqual(rewrite.citation_problem(o, r), "(invented reference)", r)

    def test_a_failing_llama_is_reported_not_taken_for_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            fake = os.path.join(tmp, "broken_llama.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\nsys.stderr.write('error: invalid argument: -dev\\n')\n"
                         "sys.exit(3)\n")
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("El turismo en la sierra crece cada año con más visitantes.\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "2", env=env)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("exited with code 3", r.stderr)
            self.assertIn("invalid argument: -dev", r.stderr)
            self.assertNotIn("truncated", r.stdout)

    def test_only_and_lead_are_checked_before_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_llama(tmp)
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("Uno dos tres cuatro.\n\nCinco seis siete ocho.\n")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("Uno.\n\nDos.\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            for only, message in (("5", "has 2 paragraphs"), ("a", "paragraph numbers")):
                r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--only", only,
                        env=env)
                self.assertEqual(r.returncode, 2)
                self.assertIn(message, r.stderr)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--lead", "Desde la",
                    env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("--lead needs --only", r.stderr)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("Uno.\n")
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--take", "1=" + src,
                    env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("same count", r.stderr)

    def test_max_tells_retries_and_keeps_the_try_with_fewest(self):
        text = ("Remote work changed how many offices plan their weeks, and teams now meet in "
                "person on fewer days while the rest of the work happens from home.\n")
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            fake = os.path.join(tmp, "tell_llama.py")
            calls = os.path.join(tmp, "calls")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write(
                    "import os, sys\n"
                    f"c = {calls!r}\n"
                    "n = int(open(c).read()) + 1 if os.path.exists(c) else 1\n"
                    "open(c, 'w').write(str(n))\n"
                    "outs = {1: ' work plays a crucial role in the pivotal plans of offices, and'\n"
                    "           ' crews gather on fewer days while the rest gets done at home.',\n"
                    "        2: ' work reshaped the weekly plans of offices and crucially crews'\n"
                    "           ' gather on fewer days, while the rest gets done at home now.',\n"
                    "        3: ' work altered how offices plan the week: crews gather on fewer'\n"
                    "           ' days in person and the rest of the job gets done at home.'}\n"
                    "sys.stdout.write(outs[min(n, 3)] + '\\n</target_text>')\n")
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "2",
                    "--max-tells", "0", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("crucially", read(out))  # the second try: one tell, not three
            self.assertIn("every try kept AI tells", r.stdout)
            os.remove(calls)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "3",
                    "--max-tells", "0", env=env)
            self.assertIn("altered how offices", read(out))
            self.assertIn("done, try 3", r.stdout)

    def _scripted_llama(self, tmp, script):
        """A fake llama that answers from `script`: {opening words: [answer per call]}."""
        for f in (rewrite.BASE, rewrite.ADAPTER):
            open(os.path.join(tmp, f), "w").close()
        fake = os.path.join(tmp, "scripted_llama.py")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(
                "import json, os, sys\n"
                "args = sys.argv[1:]\n"
                "prompt = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
                "src = prompt.split('<source_text>\\n')[1].split('\\n</source_text>')[0]\n"
                f"script = json.loads({json.dumps(json.dumps(script))})\n"
                f"log = {os.path.join(tmp, 'log')!r}\n"
                "with open(log, 'a', encoding='utf-8') as fh: fh.write(src[:20] + '\\n')\n"
                "key = next(k for k in script if src.startswith(k))\n"
                "n = sum(1 for ln in open(log, encoding='utf-8') if ln.startswith(src[:20]))\n"
                "out = script[key][min(n, len(script[key])) - 1]\n"
                "sys.stdout.buffer.write((out + '\\n</target_text>').encode('utf-8'))\n")
        return fake

    def _run_scripted(self, text, answers, *extra):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        fake = self._scripted_llama(tmp, answers)
        src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(text)
        env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
        r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--threads", "1",
                *extra, env=env)
        log = os.path.join(tmp, "log")
        calls = read(log).splitlines() if os.path.exists(log) else []
        return r, (read(out) if os.path.exists(out) else ""), calls

    def test_markdown_code_and_headings_stay_and_lists_keep_their_items(self):
        text = ("## Working from home\n\n"
                "```bash\npython3 install.py\n\nls\n```\n\n"
                "- Remote teams now meet in person on fewer days than before the change came.\n"
                "- Offices are planned around the weeks when the whole staff comes in.\n"
                "- Short item\n")
        script_ = {"Remote teams": [" gather in person less often than they did before that shift."],
                   "Offices are": [" now arranged around those weeks when everybody shows up at once."]}
        r, out, calls = self._run_scripted(text, script_, "--tries", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(calls), 2, calls)  # only the two list items reached the model
        self.assertEqual(out, "## Working from home\n\n```bash\npython3 install.py\n\nls\n```\n\n"
                              "- Remote teams gather in person less often than they did before that shift.\n"
                              "- Offices are now arranged around those weeks when everybody shows up at once.\n"
                              "- Short item\n")
        self.assertIn("kept (code)", r.stdout)
        self.assertIn("list, 2 of 3 items rewritten", r.stdout)

    def test_a_dropped_figure_is_retried_then_kept_with_a_warning(self):
        text = "Sales grew 40% in 2021 across all of the regions that we serve today.\n"
        lost = " a great deal in 2021 across every region that we serve right now."
        good = " by 40% in 2021 across every region that the company serves now."
        r, out, _ = self._run_scripted(text, {"Sales grew": [lost, good]}, "--tries", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("by 40% in 2021", out)
        self.assertIn("done, try 2", r.stdout)
        r, out, _ = self._run_scripted(text, {"Sales grew": [lost]}, "--tries", "1")
        self.assertIn("a great deal in 2021", out)  # kept, with the figure to put back named
        self.assertIn("Put the figure back by hand", r.stdout)
        self.assertIn("1 (40)", r.stdout)
        self.assertEqual(rewrite.numbers_lost("Hubo 1.990 votos en 2020.", "En 2020, 1990 votos."), [])

    def test_a_changed_link_or_inline_code_is_never_used(self):
        text = ("Read the guide at https://example.com/docs and run `pip install x` before you "
                "start the install on your own machine.\n")
        bad = (" manual at https://example.org/docs and run `pip install x` before starting the "
               "installation on the computer you use.")
        good = (" manual at https://example.com/docs and run `pip install x` before starting the "
                "installation on the computer you use.")
        r, out, _ = self._run_scripted(text, {"Read the": [bad, good]}, "--tries", "2")
        self.assertIn("example.com/docs", out)
        self.assertIn("done, try 2", r.stdout)
        self.assertEqual(rewrite.markup_problem(text, text.replace("`pip install x`", "pip")),
                         "(link or code changed)")
        self.assertIsNone(rewrite.markup_problem("Write to ana@example.com today.",
                                                 "Send it to ana@example.com now."))

    def test_take_warns_when_a_candidate_changed_a_figure(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out, cand = (os.path.join(tmp, n) for n in ("in.txt", "out.txt", "c.txt"))
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("Sales rose 5% in 2020 across the region.\n")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("Sales went up 5% in 2020 in the region.\n")
            with open(cand, "w", encoding="utf-8") as fh:
                fh.write("Sales went up 6% in 2020 in the region.\n")  # edited by hand
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--take", "1=" + cand)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("lost the figures 5; adds the figures 6", r.stdout)

    def test_take_keeps_the_lines_of_a_list_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out, cand = (os.path.join(tmp, n) for n in ("in.txt", "out.txt", "c.txt"))
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("Intro text here.\n\n- one thing here.\n- two things here.\n")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("Intro rewritten.\n\n- one.\n- two.\n")
            with open(cand, "w", encoding="utf-8") as fh:
                fh.write("- first thing.\n- second thing.\n")
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--take", "2=" + cand)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(read(out), "Intro rewritten.\n\n- first thing.\n- second thing.\n")

    def test_quotes_pair_in_order_and_ignore_the_apostrophe_style(self):
        o = 'Critics called the plan "naive" while supporters described it as "bold".'
        self.assertEqual(rewrite.quotations(o), [])
        self.assertIsNone(rewrite.citation_problem(o, 'Critics said "naive"; backers said "bold".'))
        self.assertIsNone(rewrite.citation_problem("“It’s over now, my friends.”",
                                                   'He said "It\'s over now, my friends."'))
        self.assertIsNone(rewrite.citation_problem("Use grew (from 5% to 30% in two years).",
                                                   "Use grew (from 5% to 30% within two years)."))
        self.assertEqual(rewrite.citation_problem("Smith wrote it.", "Smith wrote it (Jones, 2019)."),
                         "(invented reference)")

    def test_a_url_in_angle_quotes_may_lose_its_quotes(self):
        self.assertIsNone(rewrite.markup_problem("Ver «https://ejemplo.org/guia» hoy.",
                                                 "Mira https://ejemplo.org/guia hoy."))

    def test_the_percent_sign_goes_back_to_the_right_figure(self):
        self.assertEqual(rewrite.restore_percent_signs("It is 60%.", "It is 60 percent."),
                         "It is 60 percent.")
        self.assertEqual(rewrite.restore_percent_signs("Es 60%.", "Es 60 por ciento."),
                         "Es 60 por ciento.")
        self.assertEqual(rewrite.restore_percent_signs("In the 5 years, sales fell 5%.",
                                                       "Over the 5 years sales dropped 5."),
                         "Over the 5 years sales dropped 5%.")

    def test_bullets_of_six_words_or_more_are_rewritten(self):
        text = "- Faster page loads with optimized image caching\n- Fast setup\n"
        answers = {"Faster page": [" now load quicker thanks to smarter image caching."]}
        r, out, calls = self._run_scripted(text, answers, "--tries", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out, "- Faster page now load quicker thanks to smarter image caching.\n"
                              "- Fast setup\n")

    def test_a_try_that_adds_or_changes_a_figure_is_never_used(self):
        text = "Accuracy reached 0.50 on the test set after training for many more epochs.\n"
        bad = [" 0.5 on the test set once training ran for many further epochs.",
               " 0.50 on the test set in 2021 once training ran for many further epochs."]
        good = " 0.50 on the test set once training ran for many further epochs."
        r, out, _ = self._run_scripted(text, {"Accuracy reached": bad + [good]}, "--tries", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out.strip(), "Accuracy reached" + good)
        self.assertIn("done, try 3", r.stdout)

    def _echo_llama(self, tmp):
        """A fake llama that writes back a different, faithful version each call."""
        for f in (rewrite.BASE, rewrite.ADAPTER):
            open(os.path.join(tmp, f), "w").close()
        fake = os.path.join(tmp, "echo_llama.py")
        calls = os.path.join(tmp, "calls")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(
                "import os, sys\n"
                "args = sys.argv[1:]\n"
                "prompt = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
                "lead = prompt.split('<target_text>\\n')[1]\n"
                f"c = {calls!r}\n"
                "n = int(open(c).read()) + 1 if os.path.exists(c) else 1\n"
                "open(c, 'w').write(str(n))\n"
                "words = ['la semilla crece despacio', 'el árbol nace de la semilla',\n"
                "         'de la semilla sale un árbol']\n"
                "body = ' ' + words[n % 3] + ' y el lead fue ' + lead.replace(' ', '+') + ' en la vuelta ' + 'abcdefghijklmnopqrst'[n] + ' del bosque.'\n"
                "sys.stdout.buffer.write((body + '\\n</target_text>').encode('utf-8'))\n")
        return fake

    def test_candidates_are_written_and_take_adopts_one(self):
        text = ("Uno de los problemas: la semilla se convierte en árbol con el tiempo y crece.\n\n"
                "La semilla crece y se vuelve un árbol grande con los años del bosque.\n")
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._echo_llama(tmp)
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("Primero, ya corregido.\n\nSegundo, ya corregido.\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--only", "1",
                    "--candidates", "3", "--lead", "Desde la", "--threads", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            folder = out + ".candidates"
            files = sorted(os.listdir(folder))
            self.assertEqual(files, ["p01-1.txt", "p01-2.txt", "p01-3.txt"])
            first = read(os.path.join(folder, files[0]))
            self.assertTrue(first.startswith("Desde la "), first)
            self.assertIn("Desde+la", first)  # the lead reached the prompt
            self.assertEqual(read(out), "Primero, ya corregido.\n\nSegundo, ya corregido.\n")
            self.assertIn("tells 0", r.stdout)
            self.assertIn("fewest tells first", r.stdout)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out,
                    "--take", "1=" + os.path.join(folder, files[1]), env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            new = read(out).split("\n\n")
            self.assertEqual(new[0], read(os.path.join(folder, files[1])).strip())
            self.assertEqual(new[1].strip(), "Segundo, ya corregido.")

    def test_candidates_need_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._echo_llama(tmp)
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), ORIGINAL, "-o",
                    os.path.join(tmp, "x.txt"), "--candidates", "2", env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("--only", r.stderr)

    def test_recognizes_titles(self):
        self.assertTrue(rewrite.is_title("Turismo y tecnología"))
        self.assertFalse(rewrite.is_title("El turismo crece."))

    def _fake_llama(self, tmp):
        for f in (rewrite.BASE, rewrite.ADAPTER):
            open(os.path.join(tmp, f), "w").close()
        fake = os.path.join(tmp, "fake_llama.py")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(
                "import sys\n"
                "args = sys.argv[1:]\n"
                "prompt = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
                "source = prompt.split('<source_text>\\n')[1].split('\\n</source_text>')[0]\n"
                "rest = ' '.join(source.split()[2:])\n"
                "sys.stdout.buffer.write((' ' + rest + '\\n</target_text>').encode('utf-8'))\n")
        return fake

    def test_runs_end_to_end_with_a_fake_llama(self):
        """The full path of rewrite.py without the model: prompt in a UTF-8 file, output
        read as UTF-8 (on Windows, without this, accents arrived broken) and file written.
        Uses the new env variables and English flags, then the old ones."""
        text = "Año tras año, el pingüino «Nuño» camina—sin prisa—hacia el sur.\n"
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_llama(tmp)
            src, out = os.path.join(tmp, "in.txt"), os.path.join(tmp, "out.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out,
                    "--tries", "1", "--threads", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(read(out), text)
            os.remove(out)
            env = {k: v for k, v in os.environ.items()
                   if k not in ("HUMANIZE_MODEL_DIR", "HUMANIZE_LLAMA")}
            env.update(HUMANIZAR_HIP_DIR=tmp, HUMANIZAR_LLAMA=fake)
            r = run(sys.executable, script("hip.py"), src, "--salida", out,
                    "--intentos", "1", "--hilos", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("hip.py is now rewrite.py", r.stderr)
            self.assertEqual(read(out), text)

    def test_without_model_warns_and_exits_with_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp)
            r = run(sys.executable, script("rewrite.py"), ORIGINAL,
                    "-o", os.path.join(tmp, "x.txt"), env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("ERROR", r.stderr)


class Tells(unittest.TestCase):
    # Before/after pairs from github.com/blader/humanizer (MIT, © 2025 Siqi Chen)
    PAIRS = [
        ("It's not just about the beat riding under the vocals; it's part of the aggression "
         "and atmosphere. It's not merely a song, it's a statement.",
         "The heavy beat adds to the aggressive tone."),
        ("The real question is whether teams can adapt. At its core, what really matters is "
         "organizational readiness.",
         "The question is whether teams can adapt. That mostly depends on whether the "
         "organization is ready to change its habits."),
        ("Great question! Here is an overview of the French Revolution. It began in 1789 when a "
         "financial crisis and food shortages led to widespread unrest. I hope this helps! Let "
         "me know if you'd like me to expand on any section.",
         "The French Revolution began in 1789 when a financial crisis and food shortages led to "
         "widespread unrest."),
        ("The Statistical Institute of Catalonia was officially established in 1989, marking a "
         "pivotal moment in the evolution of regional statistics in Spain.",
         "The Statistical Institute of Catalonia was established in 1989, part of a wider "
         "decentralization of administrative functions in Spain."),
    ]

    def test_flags_ai_prose_and_not_its_human_rewrite(self):
        for before, after in self.PAIRS:
            self.assertGreaterEqual(tells.score(before, "en"), tells.STRONG, before)
            self.assertEqual(tells.score(after, "en"), 0, (after, tells.find(after, "en")))

    def test_quotations_are_not_the_author_s(self):
        self.assertEqual(tells.score('She called it "a testament to the age" and left.', "en"), 0)
        self.assertGreater(tells.score("She called it a testament to the age and left.", "en"), 0)

    def test_spanish_tells_and_the_word_potencia(self):
        self.assertGreaterEqual(tells.score("La ética juega un papel crucial en la vida.", "es"),
                                tells.STRONG)
        self.assertEqual(tells.score("La bellota tiene la potencia de ser encina.", "es"), 0)

    def test_the_rewrite_of_the_english_example_has_fewer_tells(self):
        total = lambda f: sum(s for _, s, _ in tells.report(tells.paragraphs_of(read(f)), "en"))  # noqa: E731
        self.assertLess(total(REWRITTEN_EN), total(ORIGINAL_EN))

    def test_suggests_a_lead_after_a_stock_connector(self):
        self.assertEqual(tells.suggested_lead("Furthermore, companies that embrace it win."),
                         "Companies that")
        self.assertEqual(tells.suggested_lead("Looking ahead, the future of work changes."),
                         "The future")
        self.assertIsNone(tells.suggested_lead("One of the most important problems is time."))

    def test_formatting_tells_and_markdown_blocks(self):
        doc = ("## 🚀 Strategic Negotiations And Global Partnerships\n\n"
               "She noted the door. She noted the lock. She filed both away for later.\n\n"
               "- **User Experience:** The interface is new.\n- 💡 **Key Insight:** Users want less.\n\n"
               "```\nWe delve into the tapestry here.\n```\n")
        parts = tells.paragraphs_of(doc)
        self.assertEqual(len(parts), 4)
        labels = [label for label, _, _ in tells.formatting(parts[0])]
        self.assertIn("emoji", labels)
        self.assertIn("Title Case heading", labels)
        self.assertEqual([label for label, _, _ in tells.formatting(parts[2])].count("bold label"), 2)
        self.assertIn("repeated opening", [label for label, _, _ in tells.find(parts[1], "en")])
        self.assertEqual(tells.score("The cat sat. The dog ran. The bird flew away.", "en"), 0)
        numbers = [i for i, _, _ in tells.report(parts, "en")]
        self.assertEqual(numbers, [2, 3])  # the heading and the code are not prose
        self.assertEqual(tells.formatting("## How the six options compare"), [])

    def test_ordinary_human_prose_is_not_flagged(self):
        for text, lang in [("The files were not publicly disclosed until 2019.", "en"),
                           ("Let me know if Tuesday works for you.", "en"),
                           ("No dudes en escribirme si necesitas algo.", "es"),
                           ("El autor —según dice— vino tarde, y su hermano —el mayor— también.", "es"),
                           ("The Old Testament and the New Testament differ.", "en"),
                           ("Kids in foster care need foster parents.", "en"),
                           ("We use robust standard errors that align with the literature.", "en"),
                           ("Queremos fomentar el empleo y potenciar la industria.", "es")]:
            self.assertFalse(tells.flagged(tells.find(text, lang)), (text, tells.find(text, lang)))
        self.assertTrue(tells.flagged(tells.find("Ultimately, there is no one-size-fits-all answer.", "en")))

    def test_long_pathological_input_stays_fast(self):
        import time
        t0 = time.time()
        tells.find("a-" * 8000, "en")
        tells.find("“" * 30000 + "x" * 30000, "en")
        rewrite.quotations("“" * 30000 + "x" * 30000)
        self.assertLess(time.time() - t0, 5)

    def test_cli_names_the_paragraphs_to_regenerate(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "text.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("A title\n\nThe cat sat on the mat and it was happy all day.\n\n"
                         "Furthermore, the dog plays a crucial role in the house as well.\n")
            r = run(sys.executable, script("tells.py"), src)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("--only 3 --candidates 6", r.stdout)
            self.assertIn('--lead "The dog"', r.stdout)
            r = run(sys.executable, script("tells.py"), src, "--max", "2")
            self.assertEqual(r.returncode, 1)
            r = run(sys.executable, script("tells.py"), ORIGINAL_EN, REWRITTEN_EN)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("total", r.stdout)


class Blocks(unittest.TestCase):
    DOC = ("# Title\n\nIntro paragraph. It has two sentences.\n\n```python\nx = 1\n\ny = 2\n```\n\n"
           "- **Speed:** pages load faster.\n- Second item that wraps\n  onto a second line.\n\n"
           "| a | b |\n|---|---|\n\n> A quote here.\n\n    indented code\n    more code\n\n---\n\nLast paragraph.\n")

    def test_kinds_and_a_fence_with_blank_lines_stays_one_block(self):
        got = [blocks.kind(b) for b in blocks.split(self.DOC)]
        self.assertEqual(got, ["heading", "prose", "code", "list", "table", "quote", "code",
                               "rule", "prose"])
        self.assertEqual(blocks.split(self.DOC)[2], "```python\nx = 1\n\ny = 2\n```")

    def test_an_indented_first_line_is_a_paragraph_not_code(self):
        essay = "\tMoreover, the results came quickly.\n\n\tThe second paragraph follows here.\n"
        self.assertEqual([blocks.kind(b) for b in blocks.split(essay)], ["prose", "prose"])
        self.assertEqual(blocks.split(essay)[0], "Moreover, the results came quickly.")

    def test_list_items_keep_markers_and_join_continuations(self):
        lst = blocks.split(self.DOC)[3]
        pairs = blocks.items(lst)
        self.assertEqual(pairs, [("- ", "**Speed:** pages load faster."),
                                 ("- ", "Second item that wraps onto a second line.")])
        self.assertEqual(blocks.rebuild(pairs),
                         "- **Speed:** pages load faster.\n- Second item that wraps onto a second line.")
        self.assertEqual(blocks.items("1. One.\n2) Two.\n- [x] Done."),
                         [("1. ", "One."), ("2) ", "Two."), ("- [x] ", "Done.")])

    def test_fences_close_their_block_and_an_intro_line_leads_its_list(self):
        got = blocks.split("Run this:\n```\nls\n```\nThen read the output. It is short.\n")
        self.assertEqual(got, ["Run this:", "```\nls\n```", "Then read the output. It is short."])
        intro = "Three things matter:\n- the price of the plan.\n- the time it takes."
        self.assertEqual(blocks.kind(intro), "list")
        self.assertEqual(blocks.items(intro)[0], ("", "Three things matter:"))
        self.assertEqual(blocks.kind("Hi John,\nthanks for the call.\n- not a list here"), "prose")

    def test_plain_paragraphs_split_as_before(self):
        for f in (ORIGINAL, REWRITTEN, ORIGINAL_EN, REWRITTEN_EN):
            text = read(f)
            self.assertEqual(blocks.split(text),
                             [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()])


REVERSING_LLAMA = (
    "import re, sys\n"
    "args = sys.argv[1:]\n"
    "prompt = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
    "src = prompt.split('<source_text>\\n')[1].split('\\n</source_text>')[0]\n"
    "rest = ' '.join(src.split()[2:])\n"
    "# every word changes; placeholders, figures and punctuation stay\n"
    "out = re.sub(r'[A-Za-z]{2,}', lambda m: m.group(0)[::-1], rest)\n"
    "sys.stdout.buffer.write((' ' + out + '\\n</target_text>').encode('utf-8'))\n")


class Review(unittest.TestCase):
    """Step 6's sheet: the original's sentences beside the rewrite's, flagged."""

    def test_sentences_ignore_abbreviations(self):
        import review
        self.assertEqual(review.sentences("As Smith et al. show in Fig. 3, it works. It ends."),
                         ["As Smith et al. show in Fig. 3, it works.", "It ends."])

    def test_alignment_handles_merges_splits_drops_and_additions(self):
        import review
        a = ["The plant runs on a microgrid every hour.", "Six agents control the battery.",
             "A supervisor picks a directive at midnight.", "Profit rose by six percent overall."]
        b = ["Every hour the plant runs on a microgrid, and six agents control the battery.",
             "At midnight a supervisor picks a directive.", "Weather data came from a station."]
        pairs = review.align(a, b)
        self.assertEqual(pairs[0], (a[:2], b[:1]))              # two merged into one
        self.assertEqual(pairs[1], (a[2:3], b[1:2]))
        kinds = [(len(o), len(n)) for o, n in pairs[2:]]
        self.assertIn((1, 0), kinds)                            # profit sentence dropped
        self.assertIn((0, 1), kinds)                            # weather sentence added

    def test_the_sheet_flags_what_real_runs_got_wrong(self):
        original = ("Three optimisers use a large language model (LLM) on 30 agent teams. "
                    "Its first proposals, made after only the incumbent has been scored, may help. "
                    "Neither superiority nor equivalence is established at B = 3.\n")
        rewritten = ("Three optimisers use an LLM on 30 teams of three agents. "
                     "Its first proposals, generated without having seen the incumbent, help. "
                     "There is no significant difference at B = 3.\n")
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c, out = (os.path.join(tmp, n) for n in ("o.txt", "r.txt", "c.txt", "rev.md"))
            for path, body in ((a, original), (b, rewritten), (c, "incumbent\n")):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(body)
            r = run(sys.executable, script("review.py"), a, b, "--concepts", c, "-o", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            sheet = read(out)
            self.assertIn("CONCEPT missing from the paragraph: large language model (LLM)", sheet)
            self.assertIn("FIGURES added three", sheet)
            self.assertIn("NEGATION added «without having»", sheet)
            self.assertIn("hedge dropped «may»", sheet)
            self.assertIn("added «significant»", sheet)
            self.assertIn("3 pairs, 3 flagged", r.stdout)

    def test_a_flagged_pair_names_its_part(self):
        original = "The plant runs on a microgrid every hour of the day. Profit rose by 5.7% at B = 3.\n"
        rewritten = "Each hour of the day the plant runs on a microgrid. Profit went up by 6.7% at B = 3.\n"
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "o.txt"), os.path.join(tmp, "r.txt")
            for path, body in ((a, original), (b, rewritten)):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(body)
            with open(b + ".parts.json", "w", encoding="utf-8") as fh:
                json.dump({"1": {"source": ["x", "y"], "text": ["Each hour of the day the plant runs on a microgrid.",
                                                                 "Profit went up by 6.7% at B = 3."]}}, fh)
            r = run(sys.executable, script("review.py"), a, b)
            self.assertIn("FIGURES lost 5.7; added 6.7", r.stdout)
            self.assertIn("--only 1 --part 2", r.stdout)
            self.assertNotIn("--part 1", r.stdout)                # an unflagged pair names no part

    def test_check_reports_claim_strength(self):
        self.assertEqual(check.claim_changes("The results may suggest a trend.",
                                             "The results clearly demonstrate a trend."),
                         (["may", "suggest"], ["clearly", "demonstrate"]))
        self.assertEqual(check.claim_changes("It may work.", "It might work, maybe."), ([], []))
        self.assertEqual(check.claim_changes("Los datos sugieren un efecto.",
                                             "Los datos demuestran un efecto significativo."),
                         (["sugieren"], ["demuestran", "significativo"]))


class References(unittest.TestCase):
    """A manuscript's references are never rewritten: they go to the frame, byte for byte."""
    ENTRY = "[1] A. Smith, B. Lee. Microgrid control with deep learning. IEEE Trans., 2021."

    def _prose(self, text):
        frame, paras = blocks.parse(text)
        self.assertEqual(blocks.unparse(frame, paras), text)
        return paras

    def test_markdown_references_until_the_next_heading(self):
        text = ("# Results\n\nProfit rose by 5.7%.\n\n## References\n\n" + self.ENTRY +
                "\n\n1. Wang, C. (2022). Budgeted search. Energy.\n\n## Appendix A\n\n"
                "The appendix is prose.\n")
        self.assertEqual(self._prose(text), ["# Results", "Profit rose by 5.7%.", "## Appendix A",
                                             "The appendix is prose."])

    def test_plain_title_lines_in_english_and_spanish(self):
        for title in ("REFERENCES", "6. References", "Bibliografía", "Referencias bibliográficas:",
                      "**Bibliography**", "Works Cited"):
            text = "The paper ends here.\n\n" + title + "\n\n" + self.ENTRY + "\n"
            self.assertEqual(self._prose(text), ["The paper ends here."], title)

    def test_a_thesis_chapter_after_its_references_is_rewritten(self):
        text = ("Chapter two ends.\n\nReferences\n\n" + self.ENTRY +
                "\n\nChapter 3\n\nThe third chapter is prose.\n")
        self.assertEqual(self._prose(text), ["Chapter two ends.", "Chapter 3",
                                             "The third chapter is prose."])

    def test_a_paragraph_that_mentions_references_is_not_a_heading(self):
        text = "The references in this field are few, and most are old.\n\nMore prose.\n"
        self.assertEqual(len(self._prose(text)), 2)

    def test_rewrite_leaves_the_references_alone(self):
        text = "Profit rose by 5.7% at the plant.\n\n## References\n\n" + self.ENTRY + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\nsys.stdout.write(' went up by 5.7% at the plant floor.\\n</target_text>')\n")
            src, out = os.path.join(tmp, "in.md"), os.path.join(tmp, "out.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "1",
                    "--max-copied", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(read(out).endswith("## References\n\n" + self.ENTRY + "\n"), read(out))
            self.assertIn("Paragraph 1 of 1", r.stdout)


class Latex(unittest.TestCase):
    def test_parse_and_unparse_give_the_file_back(self):
        texts = [read(PAPER), "No document environment. Just text.\n\nSecond.\n",
                 "\\begin{document}\n\\iffalse\nhidden\n\\fi\nText $x$.\n\\[ y \\]\nMore.\n"
                 "$$ z $$\n% c\n\\begin{itemize}\n\\item a \\begin{enumerate}\\item b\\end{enumerate}\n"
                 "\\end{itemize}\n\\end{document}\n"]
        for t in texts:
            frame, paras = latex.parse(t)
            self.assertEqual(latex.unparse(frame, paras), t)
        _, paras = latex.parse(texts[2])
        self.assertEqual(paras, ["Text $x$.", "More."])  # \iffalse, math, nested list kept

    def test_the_paper_prose_is_found_and_the_rest_is_frame(self):
        frame, paras = latex.parse(read(PAPER))
        self.assertEqual(len(paras), 7)
        self.assertTrue(paras[0].startswith("Remote work has fundamentally"))  # the abstract
        self.assertTrue(latex.is_list(paras[3]))
        body = "".join(frame)
        for kept in ("\\begin{equation}", "\\begin{table}", "\\begin{figure}", "\\section{Method}",
                     "\\begin{thebibliography}", "% Preamble comment"):
            self.assertIn(kept, body)

    def test_protect_and_restore(self):
        p = ("Prior work by Mart\\'{\\i}nez et al.~\\cite{m19} used $y = \\beta x$ and 60\\% of "
             "``data'' --- see Fig.~\\ref{f}. % note\nNext \\emph{line} here.")
        visible, pieces = latex.protect(p)
        self.assertEqual(visible, "Prior work by Martínez et al. [1] used [2] and 60% of “data” — "
                                  "see Fig. [3]. [4] Next [5] here.")
        back = latex.restore(visible, pieces)
        self.assertIn("Martínez et al.~\\cite{m19} used $y = \\beta x$ and 60\\% of ``data'' --- see "
                      "Fig.~\\ref{f}. % note\n", back)
        self.assertIn("Next \\emph{line} here.", back)
        self.assertEqual(latex.problem(visible, visible.replace(" [2]", ""), pieces), "(LaTeX changed)")
        self.assertEqual(latex.problem(visible, visible + " [2]", pieces), "(LaTeX changed)")
        self.assertEqual(latex.problem(visible, visible + " [9]", pieces), "(LaTeX changed)")
        self.assertEqual(latex.problem(visible, visible + " \\bf", pieces), "(LaTeX changed)")
        self.assertIsNone(latex.problem(visible, "[3] and [1] [2] [4] [5] moved.", pieces))

    def test_verb_and_control_spaces(self):
        visible, pieces = latex.protect("Run \\verb|a b| as shown, e.g.\\ the default.")
        self.assertEqual(visible, "Run [1] as shown, e.g. the default.")
        self.assertEqual(pieces[1], "\\verb|a b|")

    def test_sentences_go_on_their_own_line_but_not_inside_math_or_comments(self):
        t = "One sentence here. Two by Smith et al. Three $a. B$ four. % x. Y\nFive."
        self.assertEqual(latex.sentence_lines(t),
                         "One sentence here.\nTwo by Smith et al. Three $a. B$ four. % x. Y\nFive.")

    def _rewrite_paper(self, tmp, *extra):
        for f in (rewrite.BASE, rewrite.ADAPTER):
            open(os.path.join(tmp, f), "w").close()
        fake = os.path.join(tmp, "reversing_llama.py")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(REVERSING_LLAMA)
        src, out = os.path.join(tmp, "paper.tex"), os.path.join(tmp, "01-rewritten.tex")
        shutil.copy(PAPER, src)
        env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
        r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "1",
                "--threads", "1", *extra, env=env)
        return r, src, out

    def test_rewrite_and_join_a_paper_keep_its_latex_and_every_figure(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, src, out = self._rewrite_paper(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("Paragraph 4 of 7: list, 2 of 2 items rewritten", r.stdout)
            original, rewritten = read(src), read(out)
            self.assertEqual(latex.parse(rewritten)[0], latex.parse(original)[0])  # frame
            self.assertIn("degnahc", rewritten)  # the prose did change
            for kept in ("~\\cite{smith2020,lee2021}", "~\\ref{fig:trend}", "$y = \\alpha + \\beta x$",
                         "12\\% ni 2019", "\\emph{14}", "~\\eqref{eq:main}", "% TODO: update\n"):
                self.assertIn(kept, rewritten)
            final = os.path.join(tmp, "02-final.tex")
            r = run(sys.executable, script("join.py"), out, "-o", final, "--pauses", "2")
            self.assertEqual(r.returncode, 0, r.stderr)
            r = run(sys.executable, script("check.py"), src, out, final)
            self.assertIn("FIGURES: all 45 of the original are in every version, none added.", r.stdout)
            if HAS_PDFLATEX:
                pdf = os.path.join(tmp, "final.pdf")
                r = run(sys.executable, script("convert.py"), final, "-o", pdf)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_try_that_breaks_a_placeholder_is_not_used(self):
        text = ("\\begin{document}\nPrior work by Smith~\\cite{s20} measured the output of "
                "teams with a model $y = x$ over many years.\n\\end{document}\n")
        dropped = " by Smith measured how teams produce with a model [2] across many years."
        good = " by Smith [1] measured how teams produce with a model [2] across many years."
        with tempfile.TemporaryDirectory() as tmp:
            fake = Rewrite._scripted_llama(self, tmp, {"Prior work": [dropped, good]})
            src, out = os.path.join(tmp, "in.tex"), os.path.join(tmp, "out.tex")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(text)
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "2", env=env)
            self.assertIn("done, try 2", r.stdout)
            self.assertIn("Prior work by Smith~\\cite{s20} measured how teams produce with a model "
                          "$y = x$ across many years.", read(out))

    def test_tells_and_check_read_the_prose_of_a_paper(self):
        r = run(sys.executable, script("tells.py"), PAPER)
        self.assertIn("fundamentally reshaped", r.stdout)
        self.assertIn("00-original.tex -o 01-rewritten.tex", r.stdout)
        self.assertNotIn("alpha", r.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            conc = os.path.join(tmp, "c.txt")
            with open(conc, "w", encoding="utf-8") as fh:
                fh.write("Martínez\n")
            r = run(sys.executable, script("check.py"), PAPER, PAPER, "--concepts", conc)
            self.assertEqual(r.returncode, 0, r.stdout)  # «Mart\\'{\\i}nez» is «Martínez»


class Convert(unittest.TestCase):
    PAGES = ["Journal of Tests 12 (2026)\nAn Interesting Title\nAbstract\nRemote work has changed "
             "how teams plan their weeks, and the effect on inter-\nnational firms is large. The "
             "self-reported output rose by 7.5% in 2021.\n\x88 A first item of the list here.\n"
             "\x88 A second item of the list here.\ny = α + βx\n(1)\n2\nResults\nThe cost "
             "was\n38\n1\n",
             "Journal of Tests 12 (2026)\nThis paragraph continues the page and ends with a full "
             "stop after all these words.\n2\n",
             "Journal of Tests 12 (2026)\nReferences\n[1] J. Smith. Working apart. 2020.\n3\n"]

    def test_text_from_pdf_pages(self):
        md = convert.pdf_to_text(self.PAGES)
        self.assertNotIn("Journal of Tests", md)  # running header
        self.assertIn("## Abstract", md)
        self.assertIn("the effect on international firms is large. The self-reported output", md)
        self.assertIn("- A first item of the list here.\n- A second item of the list here.", md)
        self.assertIn("```text\ny = α + βx\n(1)\n```", md)
        self.assertIn("## References\n\n```text\n[1] J. Smith. Working apart. 2020.\n```", md)
        self.assertNotRegex(md, r"(?m)^[123]$")  # page numbers
        self.assertIn("## 2 Results", md)  # a section number is not a page number
        self.assertIn("38", md)  # nor is a lone figure in a table
        removed = []
        md = convert.pdf_to_text(self.PAGES, removed)
        self.assertEqual(removed.count("Journal of Tests 12 (2026)"), 3)
        lost = check.numbers_lost(convert.normalize("\n".join(self.PAGES)), md)
        self.assertEqual(sorted(lost), sorted(check.numbers_lost("\n".join(removed), "")))

    def test_text_to_latex_escapes_and_keeps_structure(self):
        tex = convert.text_to_latex("## Results\n\nCost: $5 & 10% of R_t, with α ≤ 0.5.\n\n"
                                    "- one item here\n- two\n\n```text\n[1] Ref. 2020\n```\n")
        self.assertIn("\\section*{Results}", tex)
        self.assertIn("Cost: \\$5 \\& 10\\% of R\\_t, with \\ensuremath{\\alpha} \\ensuremath{\\leq} 0.5.", tex)
        self.assertIn("\\begin{itemize}\n  \\item one item here\n  \\item two\n\\end{itemize}", tex)
        self.assertIn("\\ttfamily\n[1] Ref. 2020\n", tex)
        self.assertEqual(convert.escape("CO₂ and x⁴"), "CO\\textsubscript{2} and x\\textsuperscript{4}")

    @unittest.skipUnless(CAN_READ_PDF, "needs pdftotext")
    def test_the_example_pdf_comes_back_as_its_prose(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "paper.md")
            r = run(sys.executable, script("convert.py"), PAPER_PDF, "-o", md)
            self.assertEqual(r.returncode, 0, r.stderr)
            text = read(md)
            self.assertIn("Prior work by Martínez et al. [3] measured output", text)
            self.assertIn("- A panel of 1,200 employees observed over 24 months in 14 firms.", text)
            self.assertIn("## References", text)
            if HAS_PDFLATEX:
                pdf = os.path.join(tmp, "back.pdf")
                r = run(sys.executable, script("convert.py"), md, "-o", pdf)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertGreater(os.path.getsize(pdf), 1000)

    @unittest.skipUnless(CAN_READ_PDF and HAS_PDFLATEX, "needs pdftotext and pdflatex")
    def test_every_figure_of_the_text_is_in_the_pdf_made_from_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            md, pdf = os.path.join(tmp, "a.md"), os.path.join(tmp, "a.pdf")
            with open(md, "w", encoding="utf-8") as fh:
                fh.write("## 1 Results\n\nCO₂ fell 5% to 0.50 in 2020, with α = 0.05.\n\n"
                         "- 1,200 people in 14 firms\n\n```text\n38  90\n```\n")
            r = run(sys.executable, script("convert.py"), md, "-o", pdf)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(convert.figures_missing_from_pdf(read(md), pdf), [])

    def test_without_an_engine_it_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "a.md")
            with open(md, "w", encoding="utf-8") as fh:
                fh.write("Some text.\n")
            r = run(sys.executable, script("convert.py"), md, "-o", os.path.join(tmp, "a.pdf"),
                    env=dict(os.environ, PATH=tmp))
            self.assertEqual(r.returncode, 2)
            self.assertIn("Overleaf", r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "a.tex")))
            r = run(sys.executable, script("convert.py"), PAPER_PDF, "-o", os.path.join(tmp, "b.pdf"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("goes to text first", r.stderr)


class Clean(unittest.TestCase):
    """Step 4a: the agent edits the slop out of a work file; import is the gate."""
    SLOP = ("Moreover, our framework plays a crucial role in the evolving landscape of microgrid "
            "control. It is not just a scheduler, but a testament to what reinforcement learning "
            "can achieve. Profit rose by 5.7% at B = 3, with a 95% CI of -0.7 to +2.8.")
    PLAIN = ("The supervisor reads the scored history and proposes a directive for the day. The "
             "agents follow it until an event notice arrives, and then the supervisor is called "
             "again with the new state of the plant.")
    GOOD = ("Our framework controls a microgrid. It schedules the plant, and shows what "
            "reinforcement learning can do there. Profit rose by 5.7% at B = 3, with a 95% CI "
            "of -0.7 to +2.8.")

    def _run(self, original, edits, ext=".txt", concepts="microgrid\nreinforcement learning\n"):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        src, work, out, conc = (os.path.join(tmp, n) for n in
                                ("00-original" + ext, "00-slop.txt", "00-clean" + ext, "c.txt"))
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(original)
        with open(conc, "w", encoding="utf-8") as fh:
            fh.write(concepts)
        r = run(sys.executable, script("clean.py"), "export", src, "-o", work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = read(work)
        for old, new in edits:
            self.assertIn(old, text)
            text = text.replace(old, new)
        with open(work, "w", encoding="utf-8") as fh:
            fh.write(text)
        r = run(sys.executable, script("clean.py"), "import", src, work, "-o", out, "--concepts", conc)
        return r, (read(out) if os.path.exists(out) else None)

    def test_a_cleanup_of_the_slop_passes_and_keeps_the_rest(self):
        original = "# Results\n\n" + self.SLOP + "\n\n" + self.PLAIN + "\n"
        r, out = self._run(original, [(self.SLOP, self.GOOD)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out, "# Results\n\n" + self.GOOD + "\n\n" + self.PLAIN + "\n")
        self.assertIn("tells score", r.stdout)
        self.assertIn("2  - Moreover, our framework plays a crucial role", r.stdout)
        self.assertIn("+ Our framework controls a microgrid. It schedules", r.stdout)
        self.assertEqual(clean.changed_sentences("A b. C d. E f.", "A b. X y. E f."), [("C d.", "X y.")])

    def test_a_dropped_minus_or_lost_concept_writes_nothing(self):
        original = self.SLOP + "\n\n" + self.PLAIN + "\n"
        r, out = self._run(original, [(self.SLOP, self.GOOD.replace("-0.7", "0.7"))])
        self.assertEqual(r.returncode, 1)
        self.assertIsNone(out)
        self.assertIn("lost -0.7", r.stdout)
        r, out = self._run(original, [(self.SLOP, self.GOOD.replace("a microgrid", "the plant"))])
        self.assertEqual(r.returncode, 1)
        self.assertIn("concept lost: microgrid", r.stdout)

    def test_a_rewrite_is_not_a_cleanup(self):
        original = self.SLOP + "\n\n" + self.PLAIN + "\n"
        rewritten = ("A microgrid needs control, and ours does it with reinforcement learning, "
                     "which pays: at B = 3 profit went up 5.7% (95% CI -0.7 to +2.8).")
        r, out = self._run(original, [(self.SLOP, rewritten)])
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("only the slop, at most 50%", r.stdout)
        self.assertIsNone(out)

    def test_the_whole_text_has_a_limit_too(self):
        a = ("The plant runs every hour. The supervisor picks a directive. Profit rose by 5.7% "
             "in the microgrid test.")
        b = ("Each hour the plant runs. A directive is picked by the supervisor. In the "
             "microgrid test profit went up by 5.7%.")
        r, out = self._run(a + "\n", [(a, b)], concepts="microgrid\n")
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_latex_placeholders_must_stay(self):
        tex = ("\\documentclass{article}\n\\begin{document}\n"
               "Moreover, the method plays a crucial role in microgrid control~\\cite{a}, with "
               "$p = 0.24$ and a gain that we measured on every one of the thirty teams.\n"
               "\\end{document}\n")
        r, out = self._run(tex, [("Moreover, the method plays a crucial role in", "The method matters for")],
                           ext=".tex", concepts="microgrid\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("The method matters for microgrid control~\\cite{a}", out)
        self.assertIn("$p = 0.24$", out)
        self.assertTrue(out.startswith("\\documentclass{article}"))
        r, out = self._run(tex, [("control [1]", "control")], ext=".tex", concepts="microgrid\n")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIsNone(out)

    def test_spanish_is_left_to_the_base_model(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        src = os.path.join(tmp, "es.txt")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("Además, el marco juega un papel crucial en el control de la microrred y "
                     "de la planta, que es lo que el estudio quiere mostrar.\n")
        r = run(sys.executable, script("clean.py"), "export", src, "-o", os.path.join(tmp, "w.txt"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("for English text", r.stderr)


W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
W_STYLES = (
    '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
    '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Capitulo"><w:name w:val="Capítulo de tesis"/>'
    '<w:basedOn w:val="Heading1"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="SourceCode"><w:name w:val="Source Code"/></w:style>')
W_ITALIC = '<w:r><w:rPr><w:i/></w:rPr><w:t>in situ</w:t></w:r>'
W_FIELD = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> ADDIN '
           'ZOTERO_ITEM CSL_CITATION {} </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/>'
           '</w:r><w:r><w:t>(Smith, 2020)</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>')
W_NOTE = '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:id="1"/></w:r>'
W_LINK = '<w:hyperlink r:id="rId9"><w:r><w:t>the dataset</w:t></w:r></w:hyperlink>'
W_RICH = ('<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:bookmarkStart w:id="0" w:name="_Ref1"/>'
          '<w:r><w:t xml:space="preserve">Measurements taken </w:t></w:r>' + W_ITALIC +
          '<w:proofErr w:type="spellStart"/><w:r><w:t xml:space="preserve"> show that the supervisor cuts '
          'costs by 12% </w:t></w:r><w:proofErr w:type="spellEnd"/>' + W_FIELD +
          '<w:r><w:t xml:space="preserve">, and </w:t></w:r>' + W_LINK +
          '<w:r><w:t xml:space="preserve"> confirms it for 30 plants.</w:t></w:r>' + W_NOTE +
          '<w:bookmarkEnd w:id="0"/></w:p>')
# A stand-in for llama.cpp on Word text: a few swaps, every placeholder kept. A source of
# more than 150 words gets a cut-off answer, so a long paragraph is redone in parts.
W_FAKE = (
    "import os, sys\n"
    "args = sys.argv[1:]\n"
    "prompt = open(args[args.index('-f') + 1], encoding='utf-8').read()\n"
    "src = prompt.split('<source_text>\\n')[1].split('\\n</source_text>')[0]\n"
    "lead = prompt.split('<target_text>\\n')[1]\n"
    "if len(src.split()) > 150:\n"
    "    out = ' and nothing else.'\n"
    "else:\n"
    "    out = src\n"
    "    for a, b in (('cuts', 'reduces'), ('show that', 'find that'), (' rose', ' went up')):\n"
    "        out = out.replace(a, b)\n"
    "    if os.environ.get('FAKE_REDO'):\n"
    "        out = out.replace('budget', 'allowance')\n"
    "    out = ' ' + ' '.join(out.split()[len(lead.split()):])\n"
    "sys.stdout.buffer.write((out + '\\n</target_text>').encode('utf-8'))\n")


def w_para(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


W_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.'
           'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType='
           '"application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" '
           'ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
           '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
           'officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" '
           'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
           '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-'
           'officedocument.wordprocessingml.footnotes+xml"/></Types>')
W_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://'
          'schemas.openxmlformats.org/package/2006/relationships">{}</Relationships>')
W_REL = ('<Relationship Id="{}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
         'relationships/{}" Target="{}"{}/>')


def make_docx(path, body):
    """A Word file built with zipfile alone: the parts the scripts read, and parts they
    must copy byte for byte."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", W_TYPES)
        z.writestr("_rels/.rels", W_RELS.format(W_REL.format("rId1", "officeDocument",
                                                             "word/document.xml", "")))
        z.writestr("word/_rels/document.xml.rels", W_RELS.format(
            W_REL.format("rId9", "hyperlink", "https://example.org/data", ' TargetMode="External"')
            + W_REL.format("rId2", "footnotes", "footnotes.xml", "")))
        z.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                   f'<w:document {W_NS}><w:body>{body}<w:sectPr/></w:body></w:document>')
        z.writestr("word/styles.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:styles {W_NS}>'
                   f'{W_STYLES}</w:styles>')
        z.writestr("word/footnotes.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:footnotes {W_NS}>'
                   '<w:footnote w:id="1"><w:p><w:r><w:t>A note of 2019.</w:t></w:r></w:p></w:footnote>'
                   '</w:footnotes>')
        z.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\n not really")


class Word(unittest.TestCase):
    BODY = (w_para("Introduction", "Heading1") + W_RICH
            + w_para("A plain paragraph of body text that the model rewrites, with words enough.")
            + w_para("Figure 1. The plant layout.", "Caption")
            + w_para("Introduction ........ 1", "TOC1")
            + w_para("Quoted words stay exactly as the author wrote them in the source.", "Quote")
            + w_para("x = run(plant)", "SourceCode")
            + '<w:p><w:r><w:t xml:space="preserve">A sentence with </w:t></w:r><w:ins w:id="5" w:author="A">'
              '<w:r><w:t>a tracked insertion</w:t></w:r></w:ins><w:r><w:t xml:space="preserve"> in it.'
              '</w:t></w:r></w:p>'
            + '<w:p><w:r><w:rPr><w:b/><w:rPrChange w:id="6" w:author="A"><w:rPr/></w:rPrChange></w:rPr>'
              '<w:t>Bold that a reviewer added, tracked as a formatting change.</w:t></w:r></w:p>'
            + '<w:p><w:commentRangeStart w:id="1"/><w:r><w:t>A paragraph with a comment on it, left '
              'for the author.</w:t></w:r><w:commentRangeEnd w:id="1"/></w:p>'
            + '<w:p><m:oMathPara><m:oMath><m:r><m:t>E=mc^2</m:t></m:r></m:oMath></m:oMathPara></w:p>'
            + '<w:p/>'
            + w_para("Chapter text in a style based on Heading 1", "Capitulo")
            + '<w:tbl><w:tr><w:tc>' + w_para("A table cell is never rewritten, whatever it says.")
            + '</w:tc></w:tr></w:tbl>'
            + '<w:sdt><w:sdtPr><w:docPartObj><w:docPartGallery w:val="Table of Contents"/></w:docPartObj>'
              '</w:sdtPr><w:sdtContent>' + w_para("Contents in a control of Word's own, kept.")
            + '</w:sdtContent></w:sdt>'
            + '<w:sdt><w:sdtPr><w:alias w:val="Abstract"/></w:sdtPr><w:sdtContent>'
            + w_para("An abstract that a thesis template keeps in a content control is prose too.")
            + '</w:sdtContent></w:sdt>'
            + '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>References</w:t></w:r></w:p>'
            + w_para("Smith, J. (2020). Supervisors for plants. Energy, 9, 1–9.")
            + w_para("Part, J. (2019).")
            + w_para("Appendix A", "Heading1")
            + w_para("The appendix is prose again and gets rewritten like the body was.")
            + '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> ADDIN ZOTERO_BIBL '
              '</w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>Wang, C. '
              '(2021). Budgeted search for frozen controllers.</w:t></w:r></w:p>'
            + '<w:p><w:r><w:t>Kim, D. (2020). Directive selection under uncertainty.</w:t></w:r>'
              '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')

    def _docx(self, body=None):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        for f in (rewrite.BASE, rewrite.ADAPTER):
            open(os.path.join(tmp, f), "w").close()
        fake = os.path.join(tmp, "fake.py")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(W_FAKE)
        src = os.path.join(tmp, "00-original.docx")
        make_docx(src, self.BODY if body is None else body)
        env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
        return tmp, src, env

    def test_only_prose_paragraphs_are_rewritten(self):
        _, src, _ = self._docx()
        why = [w for _, _, w in word.classify(word.read(src))]
        self.assertEqual(why, [
            "heading", None, None, "caption", "contents", "quotation", "code", "tracked changes",
            "tracked changes", "comments", "equation", "empty", "heading",
            None,                                    # the abstract in a content control
            "heading", "bibliography", "bibliography",  # a bold «References» line starts it
            "heading", None, "field", "field"])      # «Appendix A» ends it
        frame, paras = blocks.parse(blocks.read(src), "docx")
        self.assertEqual(len(paras), 4)
        self.assertTrue(all(blocks.kind(p, "docx") == "prose" for p in paras))
        self.assertIn("A table cell is never rewritten", "".join(frame))
        self.assertEqual(word.kept_counts(word.read(src)),
                         {"tracked changes": 2, "comments": 1, "field": 2})

    def test_formatting_becomes_placeholders_and_comes_back(self):
        visible, pieces = word.protect(W_RICH)
        self.assertEqual(visible, "Measurements taken [1] show that the supervisor cuts costs by 12% "
                                  "[2], and [3] confirms it for 30 plants.[4]")
        self.assertIn("ZOTERO_ITEM", pieces[2])
        self.assertIn("footnoteReference", pieces[4])
        self.assertEqual(word.text_of(word.restore(visible, pieces)), word.text_of(W_RICH))
        rewritten = "For 30 plants [3] confirms it: measurements [1] find costs 12% lower [2].[4]"
        xml = word.restore(rewritten, pieces)
        self.assertEqual(word.text_of(xml), "For 30 plants the dataset confirms it: measurements in situ "
                                            "find costs 12% lower (Smith, 2020).")
        for piece in (W_FIELD, W_LINK, '<w:footnoteReference w:id="1"/>', '<w:bookmarkStart w:id="0"'):
            self.assertEqual(xml.count(piece), 1, piece)
        self.assertNotIn("proofErr", xml)
        self.assertEqual(word.problem(visible, rewritten.replace("[2]", ""), pieces), "(Word formatting changed)")
        self.assertEqual(word.problem(visible, rewritten + " [2]", pieces), "(Word formatting changed)")
        self.assertIsNone(word.restore(rewritten.replace("[4]", "[4][4]"), pieces))
        # «[1]» typed in the text is text: the placeholders start after it
        literal = '<w:p><w:r><w:t>As [1] says, it holds </w:t></w:r>' + W_ITALIC + '</w:p>'
        visible, pieces = word.protect(literal)
        self.assertEqual(visible, "As [1] says, it holds [2]")
        self.assertEqual(word.text_of(word.restore("It holds [2], as [1] says.", pieces)),
                         "It holds in situ, as [1] says.")

    def test_a_piece_against_the_word_before_stays_against_it(self):
        p = ('<w:p><w:r><w:t xml:space="preserve">Controllers win in simulation</w:t></w:r><w:r><w:rPr>'
             '<w:vertAlign w:val="superscript"/></w:rPr><w:t>1</w:t></w:r><w:r><w:t xml:space="preserve">'
             ', and costs fall.</w:t></w:r>' + W_NOTE + '</w:p>')
        visible, pieces = word.protect(p)
        self.assertEqual(visible, "Controllers win in simulation[1], and costs fall.[2]")
        xml = word.restore("In simulation [1] controllers win, and costs fall. [2]", pieces)
        self.assertEqual(word.text_of(xml), "In simulation1 controllers win, and costs fall.")
        self.assertIn('fall.</w:t></w:r>' + W_NOTE.replace('<w:r><w:rPr>', '<w:r><w:rPr>'), xml)

    def test_writing_keeps_every_other_part_byte_for_byte(self):
        tmp, src, _ = self._docx()
        out = os.path.join(tmp, "copy.docx")
        xml = word.read(src)
        word.write(out, xml.replace("plain paragraph", "short paragraph"), src)
        with zipfile.ZipFile(src) as a, zipfile.ZipFile(out) as b:
            self.assertEqual(a.namelist(), b.namelist())
            for name in a.namelist():
                if name != "word/document.xml":
                    self.assertEqual(a.read(name), b.read(name), name)
            self.assertIn(b"short paragraph", b.read("word/document.xml"))

    def test_a_word_file_through_the_pipeline(self):
        tmp, src, env = self._docx()
        out, final = os.path.join(tmp, "01-rewritten.docx"), os.path.join(tmp, "02-final.docx")
        r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "2",
                "--max-copied", "1", "--threads", "1", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 paragraphs with tracked changes, 1 paragraphs with comments", r.stdout)
        frame_a, paras_a = blocks.parse(blocks.read(src), "docx")
        frame_b, paras_b = blocks.parse(blocks.read(out), "docx")
        self.assertEqual(frame_a, frame_b)  # headings, tables, references, fields: untouched
        rich = paras_b[0]
        self.assertIn("the supervisor reduces costs by 12%", word.text_of(rich))
        for piece in ('<w:i/>', W_FIELD, W_LINK, '<w:footnoteReference w:id="1"/>'):
            self.assertEqual(rich.count(piece), 1, piece)
        with zipfile.ZipFile(src) as a, zipfile.ZipFile(out) as b:
            self.assertEqual(a.read("word/footnotes.xml"), b.read("word/footnotes.xml"))
        r = run(sys.executable, script("check.py"), src, out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FIGURES: all", r.stdout)
        r = run(sys.executable, script("join.py"), out, "-o", final, "--pauses", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(blocks.parse(blocks.read(final), "docx")[0], frame_a)
        sheet = os.path.join(tmp, "01-review.md")
        r = run(sys.executable, script("review.py"), src, out, "-o", sheet)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("the supervisor reduces costs by 12% (Smith, 2020)", read(sheet))
        r = run(sys.executable, script("tells.py"), src, out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        work = os.path.join(tmp, "00-slop.txt")
        r = run(sys.executable, script("clean.py"), "export", src, "-o", work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("=== 1 ===\nMeasurements taken [1] show", read(work))

    def test_a_long_word_paragraph_is_rewritten_in_parts(self):
        sentences = [f"In week {n} the plant budget rose by {n}% and the supervisor kept every agent "
                     f"on the same plan." for n in range(1, 13)]
        sentences[1] = sentences[1].replace("the same plan.", "the same plan </w:t></w:r>" + W_ITALIC
                                            + '<w:r><w:t xml:space="preserve">.')
        sentences[6] = sentences[6].replace("plan.", "plan </w:t></w:r>" + W_FIELD
                                            + '<w:r><w:t xml:space="preserve">.')
        body = w_para("Results", "Heading1") + w_para(" ".join(sentences))
        tmp, src, env = self._docx(body)
        out = os.path.join(tmp, "01-rewritten.docx")
        r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--tries", "2",
                "--max-copied", "1", "--threads", "1", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("rewriting it in 3 parts", r.stdout)
        paras = blocks.parse(blocks.read(out), "docx")[1]
        self.assertEqual(len(paras), 1)  # one paragraph, as the original
        text = word.text_of(paras[0])
        self.assertEqual(text.count("went up"), 12)
        self.assertEqual(paras[0].count(W_FIELD), 1)
        self.assertEqual(paras[0].count("<w:i/>"), 1)
        saved = json.loads(read(out + ".parts.json"))
        self.assertEqual(len(saved["1"]["text"]), 3)
        # a fix in part 1 keeps the record true, so part 2 can still be redone alone
        r = run(sys.executable, script("fix.py"), out, "1", "week 1 the plant", "week 1 the factory")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(sys.executable, script("rewrite.py"), src, "-o", out, "--only", "1", "--part", "2",
                "--tries", "1", "--max-copied", "1", "--threads", "1", env=dict(env, FAKE_REDO="1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = word.text_of(blocks.parse(blocks.read(out), "docx")[1][0])
        self.assertIn("week 1 the factory", text)
        self.assertEqual(text.count("allowance"), 5)  # part 2: sentences 6 to 10
        self.assertEqual(text.count("in situ"), 1)
        self.assertEqual(text.count("(Smith, 2020)"), 1)


    @unittest.skipUnless(convert.office() and CAN_READ_PDF, "needs LibreOffice and pdftotext")
    def test_a_word_file_becomes_a_pdf_with_its_figures(self):
        tmp, src, _ = self._docx()
        pdf = os.path.join(tmp, "02-final.pdf")
        r = run(sys.executable, script("convert.py"), src, "-o", pdf)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("12%", "".join(convert.pdf_pages(pdf)))


class Fix(unittest.TestCase):
    def test_one_to_three_words_in_one_paragraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "01-rewritten.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("The majority of workers stayed home.\n\nThey split their time, and most stayed.\n")
            r = run(sys.executable, script("fix.py"), path, "1", "The majority of", "Many")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(read(path), "Many workers stayed home.\n\nThey split their time, and most "
                                         "stayed.\n")
            r = run(sys.executable, script("fix.py"), path, "2", "split their time", "were forced to "
                    "work from home all week")
            self.assertEqual(r.returncode, 1)
            self.assertIn("a fix is one to 3", r.stderr)
            r = run(sys.executable, script("fix.py"), path, "2", "st", "x")
            self.assertEqual(r.returncode, 1)
            self.assertIn("2 times", r.stderr)
            r = run(sys.executable, script("fix.py"), path, "3", "a", "b")
            self.assertEqual(r.returncode, 2)
        self.assertEqual(fix.changed_words("the majority", "many"), 2)
        self.assertEqual(fix.changed_words("of workers", "of the workers"), 1)

    def test_a_word_fix_changes_words_not_formatting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "01-rewritten.docx")
            make_docx(path, w_para("Introduction", "Heading1") + W_RICH)
            r = run(sys.executable, script("fix.py"), path, "1", "--show")
            self.assertIn("cuts costs by 12% [2], and [3]", r.stdout)
            self.assertIn("[2] = «(Smith, 2020)»", r.stdout)
            r = run(sys.executable, script("fix.py"), path, "1", "cuts costs", "lowers costs")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            p = blocks.parse(blocks.read(path), "docx")[1][0]
            self.assertIn("the supervisor lowers costs by 12% (Smith, 2020)", word.text_of(p))
            self.assertEqual(p.count(W_FIELD), 1)
            r = run(sys.executable, script("fix.py"), path, "1", "12% [2],", "12%,")
            self.assertEqual(r.returncode, 1)
            self.assertIn("keeps every [n]", r.stderr)

class ModelDir(unittest.TestCase):
    def _put_model(self, directory):
        os.makedirs(directory, exist_ok=True)
        for f in rewrite.MODEL_FILES:
            open(os.path.join(directory, f), "w").close()

    def test_default_is_the_folder_every_version_used(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(rewrite.resolve_model_dir({}, home),
                             os.path.join(home, ".cache", "humanizar-es", "hip"))

    def test_env_variables_win_new_before_old(self):
        with tempfile.TemporaryDirectory() as home:
            self._put_model(os.path.join(home, ".cache", "humanizar-es", "hip"))
            self.assertEqual(rewrite.resolve_model_dir({"HUMANIZAR_HIP_DIR": "/old"}, home), "/old")
            self.assertEqual(rewrite.resolve_model_dir(
                {"HUMANIZAR_HIP_DIR": "/old", "HUMANIZE_MODEL_DIR": "/new"}, home), "/new")


class OldNames(unittest.TestCase):
    def test_unir_shim_matches_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            new, old = os.path.join(tmp, "new.txt"), os.path.join(tmp, "old.txt")
            r1 = run(sys.executable, script("join.py"), REWRITTEN, "-o", new,
                     "--concepts", CONCEPTS)
            r2 = run(sys.executable, script("unir.py"), REWRITTEN, "-o", old,
                     "--conceptos", CONCEPTS)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertIn("unir.py is now join.py", r2.stderr)
            self.assertEqual(read(old), read(new))
            self.assertEqual(read(old), read(FINAL))

    def test_verificar_fidelidad_shim_matches_check(self):
        args = (ORIGINAL, REWRITTEN, FINAL)
        r1 = run(sys.executable, script("check.py"), *args, "--concepts", CONCEPTS)
        r2 = run(sys.executable, script("verificar_fidelidad.py"), *args, "--conceptos", CONCEPTS)
        self.assertEqual(r2.returncode, r1.returncode)
        self.assertEqual(r2.stdout, r1.stdout)
        self.assertIn("verificar_fidelidad.py is now check.py", r2.stderr)

    def test_hip_and_instalar_hip_shims_reach_the_new_scripts(self):
        r = run(sys.executable, script("hip.py"), "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--tries", r.stdout)
        # No llama.cpp (a path that does not exist): it stops before downloading anything.
        env = dict(os.environ, HUMANIZE_LLAMA=os.path.join(ROOT, "does-not-exist"))
        r = run(sys.executable, script("instalar_hip.py"), env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("instalar_hip.py is now install_model.py", r.stderr)
        self.assertIn("llama.cpp is missing", r.stdout)

    def test_shims_can_still_be_imported(self):
        import unir
        import verificar_fidelidad
        self.assertIs(unir.join_text, join.join_text)
        self.assertIs(verificar_fidelidad.negations, check.negations)

    @unittest.skipUnless(shutil.which("bash") and os.name == "posix", "macOS and Linux shortcut")
    def test_instalar_hip_sh_shim_execs_install_model_sh(self):
        s = read(script("instalar_hip.sh"))
        self.assertIn("install_model.sh", s)
        r = run("bash", "-n", script("instalar_hip.sh"))
        self.assertEqual(r.returncode, 0, r.stderr)


INSTALL = (sys.executable, os.path.join(ROOT, "install.py"))


class Installer(unittest.TestCase):
    def test_installs_and_uninstalls(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run(*INSTALL, "--dest", tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            dest = os.path.join(tmp, "humanize-research")
            for f in ("SKILL.md", "scripts/rewrite.py", "scripts/join.py", "scripts/check.py",
                      "scripts/install_model.py", "scripts/unir.py", "examples/en/2-final.txt"):
                self.assertTrue(os.path.isfile(os.path.join(dest, f)), f)
            self.assertFalse(os.path.exists(os.path.join(dest, "tests")))
            if os.name == "posix":
                self.assertTrue(os.access(os.path.join(dest, "scripts", "install_model.sh"), os.X_OK))
            run(*INSTALL, "--destino", tmp, "--desinstalar")
            self.assertFalse(os.path.exists(dest))

    def test_a_symlinked_install_can_be_replaced_by_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "skills")
            r = run(sys.executable, os.path.join(ROOT, "install.py"), "--dest", dest, "--symlink")
            if "could not create the link" in r.stdout:
                self.skipTest("no symlinks here")
            r = run(sys.executable, os.path.join(ROOT, "install.py"), "--dest", dest)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(os.path.islink(os.path.join(dest, "humanize-research")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "humanize-research", "SKILL.md")))

    def test_removes_an_install_under_the_old_test_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "humanize-local")
            os.makedirs(os.path.join(old, "scripts"))
            with open(os.path.join(old, "SKILL.md"), "w") as fh:
                fh.write("---\nname: humanize-local\n---\n")
            r = run(*INSTALL, "--dest", tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(os.path.exists(old))
            self.assertIn("removed old version: " + old, r.stdout)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "humanize-research", "SKILL.md")))
            os.makedirs(old)  # uninstalling also cleans it up
            r = run(*INSTALL, "--dest", tmp, "--uninstall")
            self.assertFalse(os.path.exists(old))
            self.assertFalse(os.path.exists(os.path.join(tmp, "humanize-research")))

    def test_an_install_under_the_old_name_is_replaced_but_not_a_git_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "humanizar-es")
            os.makedirs(os.path.join(old, "scripts"))
            with open(os.path.join(old, "SKILL.md"), "w") as fh:
                fh.write("---\nname: humanizar-es\n---\n")
            r = run(*INSTALL, "--dest", tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("removed old version: " + old, r.stdout)
            self.assertFalse(os.path.exists(old))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "humanize-research", "SKILL.md")))
            os.makedirs(os.path.join(old, ".git"))  # someone's clone under the old name
            r = run(*INSTALL, "--dest", tmp)
            self.assertIn("left as it is (a git clone): " + old, r.stdout)
            self.assertTrue(os.path.isdir(os.path.join(old, ".git")))

    def test_by_default_installs_for_every_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp)
            r = run(*INSTALL, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for folder in (".claude/skills", ".agents/skills"):
                self.assertTrue(os.path.isfile(os.path.join(tmp, folder, "humanize-research", "SKILL.md")))
            run(*INSTALL, "--agent", "codex", env=env)
            self.assertTrue(os.path.isfile(os.path.join(tmp, ".codex/skills/humanize-research/SKILL.md")))
            run(*INSTALL, "--agente", "dsh", env=env)
            self.assertTrue(os.path.isfile(os.path.join(tmp, ".dsh/skills/humanize-research/SKILL.md")))
            run(*INSTALL, "--uninstall", env=env)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude/skills/humanize-research")))

    @unittest.skipUnless(shutil.which("bash") and os.name == "posix", "macOS and Linux shortcut")
    def test_the_bash_shortcut_calls_the_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run("bash", os.path.join(ROOT, "install.sh"), "--dest", tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "humanize-research", "SKILL.md")))

    def test_frontmatter_follows_the_agent_skills_format(self):
        header = read(os.path.join(ROOT, "SKILL.md")).split("---")[1]
        name = re.search(r"^name: (.+)$", header, re.M).group(1).strip()
        description = re.search(r"^description: (.+)$", header, re.M).group(1).strip()
        self.assertEqual(name, "humanize-research")
        self.assertLessEqual(len(description), 1024)

    def test_model_installer_counts_what_is_left_to_download(self):
        import install_model
        with tempfile.TemporaryDirectory() as tmp:
            full = install_model.bytes_missing(tmp)
            self.assertGreater(full, 4e9)
            with open(os.path.join(tmp, rewrite.ADAPTER), "wb"):
                pass
            with open(os.path.join(tmp, rewrite.BASE + ".part"), "wb") as fh:
                fh.write(b"x" * 1000)
            self.assertEqual(install_model.bytes_missing(tmp), install_model.SIZES[rewrite.BASE] - 1000)

    def test_model_installer_smoke_test_reports_a_broken_llama(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            fake = os.path.join(tmp, "broken_llama.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\nsys.stderr.write('error: unknown argument: -dev\\n')\n"
                         "sys.exit(1)\n")
            code = ("import sys; sys.path.insert(0, %r); import install_model; "
                    "sys.exit(install_model.smoke_test())" % SCRIPTS)
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake)
            r = run(sys.executable, "-c", code, env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("unknown argument: -dev", r.stdout)

    def test_model_download_resumes_when_the_server_closes_early(self):
        """The server sends 2 of 3 MB and closes cleanly; the installer must resume with a
        Range request, not take the file as finished, call it corrupted and delete it."""
        import contextlib
        import hashlib
        import http.server
        import io
        import threading
        import install_model
        data = os.urandom(3 << 20)
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                rng = self.headers.get("Range")
                seen.append(rng)
                start = int(rng.split("=")[1].rstrip("-")) if rng else 0
                self.send_response(206 if rng else 200)
                self.send_header("Content-Length", str(len(data) - start))
                self.end_headers()
                body = data[start:]
                self.wfile.write(body if rng else body[:2 << 20])  # the first answer is cut

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/model.gguf"
        with tempfile.TemporaryDirectory() as tmp:
            old_dir, old_sleep = install_model.rewrite.MODEL_DIR, install_model.time.sleep
            install_model.rewrite.MODEL_DIR = tmp
            install_model.time.sleep = lambda s: None
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    install_model.download("model.gguf", url, hashlib.sha256(data).hexdigest())
            finally:
                install_model.rewrite.MODEL_DIR, install_model.time.sleep = old_dir, old_sleep
            with open(os.path.join(tmp, "model.gguf"), "rb") as fh:
                self.assertEqual(fh.read(), data)
        self.assertEqual(seen, [None, f"bytes={2 << 20}-"])

    @staticmethod
    def _gguf(path, kvs):
        """A GGUF header with these (key, type, value) pairs and no tensors."""
        import struct

        def string(t):
            b = t.encode("utf-8")
            return struct.pack("<Q", len(b)) + b
        out = b"GGUF" + struct.pack("<IQQ", 3, 0, len(kvs))
        for key, kind, value in kvs:
            out += string(key) + struct.pack("<I", kind)
            if kind == 8:
                out += string(value)
            elif kind == 4:
                out += struct.pack("<I", value)
            elif kind == 9:  # an array of strings, like the tokenizer's
                out += struct.pack("<IQ", 8, len(value)) + b"".join(string(v) for v in value)
        with open(path, "wb") as fh:
            fh.write(out)

    def test_a_base_model_of_your_own_is_checked_by_its_header(self):
        import install_model
        with tempfile.TemporaryDirectory() as tmp:
            good, chat, other = (os.path.join(tmp, n) for n in ("b.gguf", "c.gguf", "o.gguf"))
            self._gguf(good, [("general.architecture", 8, "qwen3"),
                              ("tokenizer.ggml.tokens", 9, ["a", "b", "c"]),
                              ("general.name", 8, "Qwen3 4B Base"), ("qwen3.embedding_length", 4, 2560)])
            self._gguf(chat, [("general.architecture", 8, "qwen3"), ("general.name", 8, "Qwen3 4B"),
                              ("qwen3.embedding_length", 4, 2560)])
            self._gguf(other, [("general.architecture", 8, "llama"), ("general.name", 8, "Llama 3 8B"),
                               ("llama.embedding_length", 4, 4096)])
            self.assertEqual(install_model.gguf_info(good)["general.name"], "Qwen3 4B Base")
            self.assertEqual(install_model.check_base(good), (None, None))
            problem, warning = install_model.check_base(chat)
            self.assertIsNone(problem)
            self.assertIn("not a base model", warning)
            self.assertIn("needs Qwen3-4B", install_model.check_base(other)[0])
            with open(os.path.join(tmp, "junk.gguf"), "wb") as fh:
                fh.write(b"not a model")
            self.assertIn("could not be read", install_model.check_base(os.path.join(tmp, "junk.gguf"))[0])
            env = dict(os.environ, HUMANIZE_BASE_MODEL=other, HUMANIZE_MODEL_DIR=tmp,
                       HUMANIZE_LLAMA=sys.executable)
            r = run(sys.executable, script("install_model.py"), "--no-test", env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("needs Qwen3-4B", r.stdout)
            self.assertEqual(install_model.bytes_missing(tmp, own_base=True),
                             install_model.SIZES[rewrite.ADAPTER])

    def test_rewrite_uses_the_base_model_you_point_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, rewrite.ADAPTER), "w").close()  # no Qwen3-4B-Base.Q8_0.gguf here
            own = os.path.join(tmp, "my-qwen3-4b-base-q4.gguf")
            open(own, "w").close()
            log = os.path.join(tmp, "m.txt")
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\nargs = sys.argv[1:]\n"
                         f"open({log!r}, 'w').write(args[args.index('-m') + 1])\n"
                         "sys.stdout.write(' bla bla bla bla bla bla bla bla.\\n</target_text>')\n")
            src = os.path.join(tmp, "in.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("Remote teams meet in person on fewer days than they did before now.\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake, HUMANIZE_BASE_MODEL=own)
            r = run(sys.executable, script("rewrite.py"), src, "-o", os.path.join(tmp, "o.txt"),
                    "--tries", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(read(log), own)

    def test_the_cpu_unless_you_ask_for_the_gpu(self):
        cpu = ["-ngl", "0", "-dev", "none"]
        self.assertEqual(rewrite.device_args({}), cpu)
        for off in ("", "0", "no", "off"):
            self.assertEqual(rewrite.device_args({"HUMANIZE_GPU": off}), cpu, off)
        for on in ("1", "yes", "ON", "all"):
            self.assertEqual(rewrite.device_args({"HUMANIZE_GPU": on}), ["-ngl", "99"], on)
        self.assertEqual(rewrite.device_args({"HUMANIZE_GPU": "20"}), ["-ngl", "20"])
        pinned = {"HUMANIZE_GPU": "1", "HUMANIZE_GPU_DEVICE": "Vulkan1"}
        self.assertEqual(rewrite.device_args(pinned), ["-ngl", "99", "-dev", "Vulkan1"])
        self.assertEqual(rewrite.device_args({"HUMANIZE_GPU_DEVICE": "Vulkan1"}), cpu)  # off stays off

    def test_rewrite_passes_the_device_to_llama_cpp(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            log = os.path.join(tmp, "args.txt")
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\n"
                         f"open({log!r}, 'w').write(' '.join(sys.argv[1:]) + ' ')\n"
                         "sys.stdout.write(' bla bla bla bla bla bla bla bla.\\n</target_text>')\n")
            src = os.path.join(tmp, "in.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("Remote teams meet in person on fewer days than they did before now.\n")
            for gpu, used, unused in (("1", " -ngl 99 ", " -dev "), ("", " -ngl 0 -dev none ", " -ngl 99 ")):
                env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake, HUMANIZE_GPU=gpu)
                r = run(sys.executable, script("rewrite.py"), src, "-o", os.path.join(tmp, "o.txt"),
                        "--tries", "1", env=env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(used, read(log))
                self.assertNotIn(unused, read(log))

    def test_the_installer_reads_the_gpus_llama_cpp_sees(self):
        import install_model
        from unittest import mock
        gpu = "CUDA0: NVIDIA GeForce RTX 3060 (12045 MiB, 11500 MiB free)"
        cases = {
            "gpu": (f"print('Available devices:')\nprint('  {gpu}')\n", [gpu]),
            "cpu": ("print('Available devices:')\nprint('  (none)')\n", []),  # llama.cpp's own
            "bare": ("print('Available devices:')\n", []),
            "old": ("import sys\nsys.stderr.write('error: invalid argument: --list-devices\\n')\n"
                    "sys.exit(1)\n", None),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, (code, expected) in cases.items():
                fake = os.path.join(tmp, name + ".py")
                with open(fake, "w", encoding="utf-8") as fh:
                    fh.write("import sys\nsys.stderr.write('load_backend: loaded CPU backend\\n')\n" + code)
                with mock.patch.dict(os.environ, {"HUMANIZE_LLAMA": fake}):
                    self.assertEqual(install_model.gpu_devices(), expected, name)

    def test_a_bigger_model_needs_its_own_adapter(self):
        import install_model
        with tempfile.TemporaryDirectory() as tmp:
            lora, plain, base8, chat8, llama = (os.path.join(tmp, n) for n in
                                                ("lora.gguf", "plain.gguf", "b8.gguf", "c8.gguf", "l.gguf"))
            self._gguf(lora, [("general.architecture", 8, "qwen3"), ("adapter.type", 8, "lora")])
            self._gguf(plain, [("general.architecture", 8, "qwen3"), ("general.name", 8, "Qwen3 8B Base")])
            self._gguf(base8, [("general.architecture", 8, "qwen3"), ("general.name", 8, "Qwen3 8B Base"),
                               ("qwen3.embedding_length", 4, 4096)])
            self._gguf(chat8, [("general.architecture", 8, "qwen3"), ("general.name", 8, "Qwen3 8B"),
                               ("qwen3.embedding_length", 4, 4096)])
            self._gguf(llama, [("general.architecture", 8, "llama"), ("general.name", 8, "Meta Llama 3 8B"),
                               ("llama.embedding_length", 4, 4096)])
            self.assertEqual(install_model.check_adapter(lora), (None, "qwen3"))
            self.assertIn("not a LoRA adapter", install_model.check_adapter(plain)[0])
            self.assertEqual(install_model.check_base(base8, "qwen3"), (None, None))  # width 4096 is fine now
            self.assertIn("needs Qwen3-4B", install_model.check_base(base8)[0])      # not with the 4B adapter
            self.assertIn("your adapter is qwen3", install_model.check_base(llama, "qwen3")[0])
            self.assertIn("not a base model", install_model.check_base(chat8, "qwen3")[1])
            self.assertEqual(install_model.check_base(llama, "llama"), (None, None))  # Llama-3-8B base
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=sys.executable)
            r = run(sys.executable, script("install_model.py"), "--no-test",
                    env=dict(env, HUMANIZE_ADAPTER=lora))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("needs HUMANIZE_BASE_MODEL", r.stdout)
            r = run(sys.executable, script("install_model.py"), "--no-test",
                    env=dict(env, HUMANIZE_ADAPTER=lora, HUMANIZE_BASE_MODEL=base8))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # nothing to download
            self.assertIn("Your adapter:", r.stdout)
            self.assertEqual(install_model.bytes_missing(tmp, own_base=True, own_adapter=True), 0)

    def test_rewrite_uses_the_adapter_you_point_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            own_base, own_adapter = (os.path.join(tmp, n) for n in ("b8.gguf", "a8.gguf"))
            open(own_base, "w").close()
            open(own_adapter, "w").close()
            log = os.path.join(tmp, "args.txt")
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("import sys\nargs = sys.argv[1:]\n"
                         f"open({log!r}, 'w').write(args[args.index('--lora') + 1])\n"
                         "sys.stdout.write(' bla bla bla bla bla bla bla bla.\\n</target_text>')\n")
            src = os.path.join(tmp, "in.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("Remote teams meet in person on fewer days than they did before now.\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake,
                       HUMANIZE_BASE_MODEL=own_base, HUMANIZE_ADAPTER=own_adapter)
            r = run(sys.executable, script("rewrite.py"), src, "-o", os.path.join(tmp, "o.txt"),
                    "--tries", "1", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(read(log), own_adapter)

    def test_the_installer_names_only_the_pinned_gpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in (rewrite.BASE, rewrite.ADAPTER):
                open(os.path.join(tmp, f), "w").close()
            fake = os.path.join(tmp, "fake.py")
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("print('Available devices:')\nprint('  Vulkan0: Intel(R) Graphics (RPL-S)')\n"
                         "print('  Vulkan1: NVIDIA GeForce RTX 5060 Laptop GPU')\n")
            env = dict(os.environ, HUMANIZE_MODEL_DIR=tmp, HUMANIZE_LLAMA=fake, HUMANIZE_GPU="1")
            # skip the checksums of the empty stand-in files: only the summary is under test
            code = ("import sys; sys.path.insert(0, %r); import install_model as m; "
                    "m.download = lambda *a, **k: None; sys.argv = ['x', '--no-test']; "
                    "sys.exit(m.main())" % SCRIPTS)
            r = run(sys.executable, "-c", code, env=dict(env, HUMANIZE_GPU_DEVICE="Vulkan1"))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("runs on: the GPU (Vulkan1: NVIDIA", r.stdout)
            self.assertNotIn("Intel", r.stdout)
            r = run(sys.executable, "-c", code, env=dict(env, HUMANIZE_GPU_DEVICE="Vulkan7"))
            self.assertIn("HUMANIZE_GPU_DEVICE is Vulkan7", r.stdout)

    def test_a_file_that_does_not_match_is_set_aside_not_deleted(self):
        import contextlib
        import hashlib
        import http.server
        import io
        import threading
        import install_model
        data = b"the real file" * 100

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as tmp:
            mine = os.path.join(tmp, "model.gguf")
            with open(mine, "wb") as fh:
                fh.write(b"someone's own model")
            old = install_model.rewrite.MODEL_DIR
            install_model.rewrite.MODEL_DIR = tmp
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    install_model.download("model.gguf", f"http://127.0.0.1:{server.server_port}/m",
                                           hashlib.sha256(data).hexdigest())
            finally:
                install_model.rewrite.MODEL_DIR = old
            self.assertEqual(read(mine + ".mismatch"), "someone's own model")
            self.assertIn("HUMANIZE_BASE_MODEL", out.getvalue())

    def test_model_installer_has_hashes(self):
        s = read(script("install_model.py"))
        self.assertEqual(len(re.findall(r'_SHA = "[0-9a-f]{64}"', s)), 2)


if __name__ == "__main__":
    unittest.main()
