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

sys.path.insert(0, SCRIPTS)
import blocks  # noqa: E402
import check  # noqa: E402
import join  # noqa: E402
import rewrite  # noqa: E402
import tells  # noqa: E402


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

    def test_english_example_keeps_every_concept(self):
        r = run(sys.executable, script("check.py"),
                ORIGINAL_EN, REWRITTEN_EN, FINAL_EN, "--concepts", CONCEPTS_EN)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("LOST", r.stdout)

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
            self.assertIn("FIGURES from the original", r.stdout)
            self.assertIn("b.txt: 60", r.stdout)
            self.assertNotIn("1,990", r.stdout.split("FIGURES")[1])

    def test_missing_file_exits_with_two(self):
        r = run(sys.executable, script("check.py"), ORIGINAL, "does-not-exist.txt")
        self.assertEqual(r.returncode, 2)


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
                "body = ' ' + words[n % 3] + ' y el lead fue ' + lead.replace(' ', '_') + ' en la vuelta ' + str(n) + ' del bosque.'\n"
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
            self.assertIn("Desde_la", first)  # the lead reached the prompt
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
           "| a | b |\n|---|---|\n\n> A quote here.\n\n    indented code\n\n---\n\nLast paragraph.\n")

    def test_kinds_and_a_fence_with_blank_lines_stays_one_block(self):
        got = [blocks.kind(b) for b in blocks.split(self.DOC)]
        self.assertEqual(got, ["heading", "prose", "code", "list", "table", "quote", "code",
                               "rule", "prose"])
        self.assertEqual(blocks.split(self.DOC)[2], "```python\nx = 1\n\ny = 2\n```")

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
            dest = os.path.join(tmp, "humanizar-es")
            for f in ("SKILL.md", "scripts/rewrite.py", "scripts/join.py", "scripts/check.py",
                      "scripts/install_model.py", "scripts/unir.py", "examples/en/2-final.txt"):
                self.assertTrue(os.path.isfile(os.path.join(dest, f)), f)
            self.assertFalse(os.path.exists(os.path.join(dest, "tests")))
            if os.name == "posix":
                self.assertTrue(os.access(os.path.join(dest, "scripts", "install_model.sh"), os.X_OK))
            run(*INSTALL, "--destino", tmp, "--desinstalar")
            self.assertFalse(os.path.exists(dest))

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
            self.assertTrue(os.path.isfile(os.path.join(tmp, "humanizar-es", "SKILL.md")))
            os.makedirs(old)  # uninstalling also cleans it up
            r = run(*INSTALL, "--dest", tmp, "--uninstall")
            self.assertFalse(os.path.exists(old))
            self.assertFalse(os.path.exists(os.path.join(tmp, "humanizar-es")))

    def test_by_default_installs_for_every_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp)
            r = run(*INSTALL, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for folder in (".claude/skills", ".agents/skills"):
                self.assertTrue(os.path.isfile(os.path.join(tmp, folder, "humanizar-es", "SKILL.md")))
            run(*INSTALL, "--agent", "codex", env=env)
            self.assertTrue(os.path.isfile(os.path.join(tmp, ".codex/skills/humanizar-es/SKILL.md")))
            run(*INSTALL, "--agente", "dsh", env=env)
            self.assertTrue(os.path.isfile(os.path.join(tmp, ".dsh/skills/humanizar-es/SKILL.md")))
            run(*INSTALL, "--uninstall", env=env)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude/skills/humanizar-es")))

    @unittest.skipUnless(shutil.which("bash") and os.name == "posix", "macOS and Linux shortcut")
    def test_the_bash_shortcut_calls_the_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run("bash", os.path.join(ROOT, "install.sh"), "--dest", tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "humanizar-es", "SKILL.md")))

    def test_frontmatter_follows_the_agent_skills_format(self):
        header = read(os.path.join(ROOT, "SKILL.md")).split("---")[1]
        name = re.search(r"^name: (.+)$", header, re.M).group(1).strip()
        description = re.search(r"^description: (.+)$", header, re.M).group(1).strip()
        self.assertEqual(name, "humanizar-es")
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

    def test_model_installer_has_hashes(self):
        s = read(script("install_model.py"))
        self.assertEqual(len(re.findall(r'_SHA = "[0-9a-f]{64}"', s)), 2)


if __name__ == "__main__":
    unittest.main()
