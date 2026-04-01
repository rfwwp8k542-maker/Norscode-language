import argparse
import difflib
import json
import subprocess
import sys
import uuid
from pathlib import Path

from compiler.cgen import CGenerator
from compiler.loader import ModuleLoader
from compiler.semantic import SemanticAnalyzer


IR_OPS_WITH_ARG = {"PUSH", "LABEL", "JMP", "JZ", "CALL", "STORE", "LOAD"}
IR_OPS_NO_ARG = {
    "ADD",
    "SUB",
    "MUL",
    "DIV",
    "MOD",
    "EQ",
    "GT",
    "LT",
    "AND",
    "OR",
    "NOT",
    "DUP",
    "POP",
    "SWAP",
    "OVER",
    "PRINT",
    "HALT",
    "RET",
}
IR_ALL_OPS = IR_OPS_WITH_ARG | IR_OPS_NO_ARG
IR_SNAPSHOT_FIXTURE = Path("tests/ir_snapshot_cases.json")


def _resolve_source_path(source_file: str) -> Path:
    path = Path(source_file).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"Fant ikke kildefil: {path}")
    return path


def load_program(source_file: str):
    source_path = _resolve_source_path(source_file)
    loader = ModuleLoader(source_path.parent)
    loaded = loader.load_entry_file(source_path.name)

    if isinstance(loaded, tuple):
        program, alias_map = loaded
    else:
        program, alias_map = loaded, {}

    return source_path, program, alias_map


def check_program(source_file: str):
    source_path, program, alias_map = load_program(source_file)
    analyzer = SemanticAnalyzer(alias_map=alias_map)
    analyzer.analyze(program)
    return source_path, program, alias_map, analyzer


def build_program(source_file: str):
    source_path, program, alias_map, analyzer = check_program(source_file)

    cgen = CGenerator(analyzer.functions, alias_map=alias_map)
    code = cgen.generate(program)

    c_path = source_path.with_suffix(".c")
    exe_path = source_path.with_suffix("")

    c_path.write_text(code, encoding="utf-8")
    subprocess.run(["clang", str(c_path), "-o", str(exe_path)], check=True)

    return source_path, c_path, exe_path, alias_map, analyzer


def disasm_program(source_file: str):
    source_path, program, alias_map, analyzer = check_program(source_file)
    cgen = CGenerator(analyzer.functions, alias_map=alias_map)
    code = cgen.generate(program)
    return source_path, code


def tokenize_simple(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    in_comment = False

    for ch in text:
        if in_comment:
            if ch == "\n":
                in_comment = False
            continue

        if ch == "#":
            if current:
                tokens.append("".join(current))
                current.clear()
            in_comment = True
            continue

        if ch.isalnum() or ch in "_-":
            current.append(ch)
            continue

        if current:
            tokens.append("".join(current))
            current.clear()

    if current:
        tokens.append("".join(current))

    return tokens


def parse_ir_tokens(tokens: list[str], strict: bool = False) -> list[str]:
    def is_selfhost_int_token(value: str) -> bool:
        try:
            return str(int(value)) == value
        except ValueError:
            return False

    def parse_selfhost_int(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    lines: list[str] = []
    i = 0
    pc = 0
    while i < len(tokens):
        op = tokens[i]
        if strict and op not in IR_ALL_OPS:
            raise RuntimeError(f"/* feil: ukjent opcode {op} */")
        if op in IR_OPS_WITH_ARG:
            if i + 1 >= len(tokens):
                raise RuntimeError("/* feil: op mangler verdi */")
            arg_token = tokens[i + 1]
            if strict:
                if not is_selfhost_int_token(arg_token):
                    raise RuntimeError(f"/* feil: ugyldig heltallsargument {arg_token} */")
                arg_value = int(arg_token)
            else:
                arg_value = parse_selfhost_int(arg_token)
            lines.append(f"{pc}: {op} {arg_value}")
            i += 2
        else:
            lines.append(f"{pc}: {op}")
            i += 1
        pc += 1
    return lines


def _escape_no_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_selfhost_disasm(tokens: list[str], strict: bool = False) -> list[str]:
    build_dir = Path("build").resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    suffix = uuid.uuid4().hex[:8]
    source_path = build_dir / f"ir_disasm_{suffix}.no"
    c_path = source_path.with_suffix(".c")
    exe_path = source_path.with_suffix("")

    token_list = ", ".join(f'"{_escape_no_string(tok)}"' for tok in tokens)
    fn_name = "disasm_fra_tokens_strict" if strict else "disasm_fra_tokens"
    source = (
        "bruk selfhost.compiler som sh\n\n"
        "funksjon start() -> heltall {\n"
        f"    la tokens: liste_tekst = [{token_list}]\n"
        f"    skriv(sh.{fn_name}(tokens))\n"
        "    returner 0\n"
        "}\n"
    )

    try:
        source_path.write_text(source, encoding="utf-8")
        _src, _c, built_exe, _alias_map, _analyzer = build_program(str(source_path))
        result = subprocess.run(
            [str(built_exe.resolve())],
            capture_output=True,
            text=True,
            check=True,
        )
        text = result.stdout.rstrip("\n")
        return [] if not text else text.splitlines()
    finally:
        for path in (source_path, c_path, exe_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def ir_disasm_source(source_file: str, strict: bool = False, engine: str = "python"):
    source_path = _resolve_source_path(source_file)
    source = source_path.read_text(encoding="utf-8")
    tokens = tokenize_simple(source)
    if engine == "selfhost":
        disasm_lines = _run_selfhost_disasm(tokens, strict=strict)
        if strict and disasm_lines and disasm_lines[0].startswith("/* feil:"):
            raise RuntimeError(disasm_lines[0])
    else:
        disasm_lines = parse_ir_tokens(tokens, strict=strict)
    return source_path, disasm_lines


def ir_disasm_source_captured(source_file: str, strict: bool, engine: str):
    try:
        source_path, lines = ir_disasm_source(source_file, strict=strict, engine=engine)
        return source_path, True, lines, ""
    except Exception as exc:
        source_path = _resolve_source_path(source_file)
        return source_path, False, [], str(exc)


def run_program(source_file: str):
    source_path, c_path, exe_path, _alias_map, _analyzer = build_program(source_file)
    print(f"Generert C-fil: {c_path}")
    print("Kompilert med: clang")
    print(f"Kjører: {exe_path}")
    subprocess.run([str(exe_path.resolve())], check=True)
    return source_path


def discover_tests() -> list[Path]:
    tests_dir = Path("tests").resolve()
    if not tests_dir.exists():
        return []
    return sorted(p.resolve() for p in tests_dir.glob("test_*.no"))


def run_test_file(source_file: str):
    source_path, c_path, exe_path, _alias_map, _analyzer = build_program(source_file)

    result = subprocess.run(
        [str(exe_path.resolve())],
        capture_output=True,
        text=True,
    )

    return {
        "source": str(source_path),
        "c_file": str(c_path),
        "exe_file": str(exe_path),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "success": result.returncode == 0,
    }


def print_test_result(result, verbose: bool = False):
    status = "OK" if result["success"] else "FEIL"
    print(f"{status}: {result['source']}")

    if verbose or not result["success"]:
        if result["stdout"]:
            print("STDOUT:")
            print(result["stdout"], end="" if result["stdout"].endswith("\n") else "\n")
        if result["stderr"]:
            print("STDERR:")
            print(result["stderr"], end="" if result["stderr"].endswith("\n") else "\n")


def run_ir_snapshot_checks():
    fixture_path = IR_SNAPSHOT_FIXTURE.resolve()
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        cases = [(item["name"], item["source"]) for item in fixture.get("non_strict", [])]
        strict_cases = fixture.get("strict", [])
    except Exception as exc:
        return {
            "source": "IR snapshot parity (python vs selfhost)",
            "c_file": "",
            "exe_file": "",
            "returncode": 1,
            "stdout": "",
            "stderr": f"Kunne ikke lese fixture {fixture_path}: {exc}\n",
            "success": False,
        }

    mismatch_lines: list[str] = []

    for name, src in cases:
        tokens = tokenize_simple(src)
        py_lines = parse_ir_tokens(tokens, strict=False)
        sh_lines = _run_selfhost_disasm(tokens, strict=False)
        if py_lines != sh_lines:
            mismatch_lines.append(f"[{name}] non-strict mismatch")
            mismatch_lines.append("--- python")
            mismatch_lines.append("+++ selfhost")
            mismatch_lines.extend(
                difflib.unified_diff(py_lines, sh_lines, fromfile="python", tofile="selfhost", lineterm="")
            )

    for item in strict_cases:
        name = item.get("name", "strict_case")
        src = item.get("source", "")
        expected_error = item.get("expected_error")
        expected_lines = item.get("expected_lines")

        tokens = tokenize_simple(src)
        py_ok = True
        py_lines: list[str] = []
        py_err = ""
        try:
            py_lines = parse_ir_tokens(tokens, strict=True)
        except Exception as exc:
            py_ok = False
            py_err = str(exc)

        sh_ok = True
        sh_lines: list[str] = []
        sh_err = ""
        try:
            sh_lines = _run_selfhost_disasm(tokens, strict=True)
            if sh_lines and sh_lines[0].startswith("/* feil:"):
                sh_ok = False
                sh_err = sh_lines[0]
                sh_lines = []
        except Exception as exc:
            sh_ok = False
            sh_err = str(exc)

        if py_ok != sh_ok or py_lines != sh_lines or py_err != sh_err:
            mismatch_lines.append(f"[{name}] strict mismatch")
            mismatch_lines.append(f"python: {'OK ' + repr(py_lines) if py_ok else py_err}")
            mismatch_lines.append(f"selfhost: {'OK ' + repr(sh_lines) if sh_ok else sh_err}")

        if expected_error is not None:
            if py_ok:
                mismatch_lines.append(f"[{name}] strict expected error but got success")
                mismatch_lines.append(f"python: OK {repr(py_lines)}")
            elif py_err != expected_error:
                mismatch_lines.append(f"[{name}] strict expected error mismatch")
                mismatch_lines.append(f"expected: {expected_error}")
                mismatch_lines.append(f"actual:   {py_err}")

        if expected_lines is not None:
            if not py_ok:
                mismatch_lines.append(f"[{name}] strict expected lines but got error")
                mismatch_lines.append(f"python error: {py_err}")
            elif py_lines != expected_lines:
                mismatch_lines.append(f"[{name}] strict expected lines mismatch")
                mismatch_lines.extend(
                    difflib.unified_diff(expected_lines, py_lines, fromfile="expected", tofile="actual", lineterm="")
                )

    success = len(mismatch_lines) == 0
    return {
        "source": "IR snapshot parity (python vs selfhost)",
        "c_file": "",
        "exe_file": "",
        "returncode": 0 if success else 1,
        "stdout": "",
        "stderr": "" if success else "\n".join(mismatch_lines) + "\n",
        "success": success,
    }


def update_ir_snapshots(check_only: bool = False):
    fixture_path = IR_SNAPSHOT_FIXTURE.resolve()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    strict_cases = fixture.get("strict", [])

    updated = 0
    for item in strict_cases:
        src = item.get("source", "")
        tokens = tokenize_simple(src)
        try:
            lines = parse_ir_tokens(tokens, strict=True)
            if item.get("expected_lines") != lines:
                updated += 1
            item["expected_lines"] = lines
            item.pop("expected_error", None)
        except Exception as exc:
            err = str(exc)
            if item.get("expected_error") != err:
                updated += 1
            item["expected_error"] = err
            item.pop("expected_lines", None)

    if not check_only:
        fixture_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return fixture_path, updated, len(strict_cases)


def run_all_tests(verbose: bool = False):
    tests = discover_tests()
    if not tests:
        raise RuntimeError("Fant ingen tester i tests/")

    results = []
    for test_file in tests:
        result = run_test_file(str(test_file))
        results.append(result)
        print_test_result(result, verbose=verbose)

    snapshot_result = run_ir_snapshot_checks()
    results.append(snapshot_result)
    print_test_result(snapshot_result, verbose=verbose)

    total = len(results)
    passed = sum(1 for r in results if r["success"])
    failed = total - passed

    print()
    print(f"Tester kjørt: {total}")
    print(f"Bestått: {passed}")
    print(f"Feilet: {failed}")

    return results


def main():
    parser = argparse.ArgumentParser(prog="python3 main.py", description="NorskLang CLI")
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="Bygg og kjør en .no-fil")
    run.add_argument("file")

    check = sub.add_parser("check", help="Parser og valider en .no-fil uten å bygge")
    check.add_argument("file")

    build = sub.add_parser("build", help="Generer C og bygg kjørbar fil")
    build.add_argument("file")

    disasm = sub.add_parser("disasm", help="Vis generert C-kode for en .no-fil")
    disasm.add_argument("file")

    ir_disasm = sub.add_parser("ir-disasm", help="Vis IR-disassembly fra tekstfil")
    ir_disasm.add_argument("file")
    ir_disasm.add_argument("--json", action="store_true", help="Skriv output som JSON")
    ir_disasm.add_argument("--strict", action="store_true", help="Feil ved ukjente opcodes/ugyldige argumenter")
    ir_disasm.add_argument("--engine", choices=["python", "selfhost"], default="python", help="Velg disasm-motor")
    ir_disasm.add_argument("--diff", action="store_true", help="Sammenlign python og selfhost disasm")
    ir_disasm.add_argument("--fail-on-warning", action="store_true", help="Feil hvis strict-resultat avviker mellom motorene")
    ir_disasm.add_argument("--save-diff", help="Lagre diff-output til fil ved --diff")

    update_snapshots = sub.add_parser("update-snapshots", help="Regenerer IR snapshot-forventninger")
    update_snapshots.add_argument("--check", action="store_true", help="Feil hvis snapshots er utdaterte (skriv ikke)")

    test = sub.add_parser("test", help="Kjør én testfil eller alle i tests/")
    test.add_argument("file", nargs="?", help="Valgfri testfil")
    test.add_argument("--verbose", action="store_true", help="Vis output også for tester som består")

    args = parser.parse_args()

    try:
        if args.cmd == "run":
            run_program(args.file)

        elif args.cmd == "check":
            source_path, _program, alias_map, analyzer = check_program(args.file)
            print(f"Kilde: {source_path}")
            print(f"Aliaser: {alias_map}")
            print("Semantikk: OK")
            print(f"Funksjoner: {list(analyzer.functions.keys())}")

        elif args.cmd == "build":
            _source_path, c_path, exe_path, _alias_map, _analyzer = build_program(args.file)
            print(f"Generert C-fil: {c_path}")
            print("Kompilert med: clang")
            print(f"Kjørbar fil: {exe_path}")

        elif args.cmd == "disasm":
            source_path, code = disasm_program(args.file)
            print(f"Kilde: {source_path}")
            print("Generert C:")
            print(code)

        elif args.cmd == "ir-disasm":
            if args.diff:
                source_path, py_ok, py_lines, py_err = ir_disasm_source_captured(args.file, strict=args.strict, engine="python")
                _source_path2, sh_ok, sh_lines, sh_err = ir_disasm_source_captured(args.file, strict=args.strict, engine="selfhost")

                diff_lines: list[str] = []
                diff_text = ""

                if py_ok != sh_ok:
                    if args.json:
                        payload = {
                            "source": str(source_path),
                            "strict": args.strict,
                            "match": False,
                            "python_ok": py_ok,
                            "python_error": py_err,
                            "selfhost_ok": sh_ok,
                            "selfhost_error": sh_err,
                        }
                        if args.save_diff:
                            diff_text = (
                                "MISMATCH (ulik feilstatus)\n"
                                f"python: {'OK' if py_ok else py_err}\n"
                                f"selfhost: {'OK' if sh_ok else sh_err}\n"
                            )
                            Path(args.save_diff).expanduser().write_text(diff_text, encoding="utf-8")
                            payload["saved_diff"] = str(Path(args.save_diff).expanduser().resolve())
                        print(json.dumps(payload, ensure_ascii=False, indent=2))
                    else:
                        print(f"Kilde: {source_path}")
                        print("Motor: diff (python vs selfhost)")
                        print("IR disasm: MISMATCH (ulik feilstatus)")
                        print(f"python: {'OK' if py_ok else py_err}")
                        print(f"selfhost: {'OK' if sh_ok else sh_err}")
                        if args.save_diff:
                            diff_text = (
                                "MISMATCH (ulik feilstatus)\n"
                                f"python: {'OK' if py_ok else py_err}\n"
                                f"selfhost: {'OK' if sh_ok else sh_err}\n"
                            )
                            save_path = Path(args.save_diff).expanduser()
                            save_path.write_text(diff_text, encoding="utf-8")
                            print(f"Diff lagret: {save_path.resolve()}")
                    sys.exit(1)

                if not py_ok and not sh_ok:
                    if py_err != sh_err:
                        if args.json:
                            payload = {
                                "source": str(source_path),
                                "strict": args.strict,
                                "match": False,
                                "python_error": py_err,
                                "selfhost_error": sh_err,
                            }
                            if args.save_diff:
                                diff_text = (
                                    "MISMATCH (ulik feilmelding)\n"
                                    f"python: {py_err}\n"
                                    f"selfhost: {sh_err}\n"
                                )
                                Path(args.save_diff).expanduser().write_text(diff_text, encoding="utf-8")
                                payload["saved_diff"] = str(Path(args.save_diff).expanduser().resolve())
                            print(json.dumps(payload, ensure_ascii=False, indent=2))
                        else:
                            print(f"Kilde: {source_path}")
                            print("Motor: diff (python vs selfhost)")
                            print("IR disasm: MISMATCH (ulik feilmelding)")
                            print(f"python: {py_err}")
                            print(f"selfhost: {sh_err}")
                            if args.save_diff:
                                diff_text = (
                                    "MISMATCH (ulik feilmelding)\n"
                                    f"python: {py_err}\n"
                                    f"selfhost: {sh_err}\n"
                                )
                                save_path = Path(args.save_diff).expanduser()
                                save_path.write_text(diff_text, encoding="utf-8")
                                print(f"Diff lagret: {save_path.resolve()}")
                        sys.exit(1)
                    raise RuntimeError(py_err)

                if args.json:
                    payload = {
                        "source": str(source_path),
                        "strict": args.strict,
                        "match": py_lines == sh_lines,
                        "python_lines": py_lines,
                        "selfhost_lines": sh_lines,
                    }
                    if args.fail_on_warning:
                        _src_w1, py_strict_ok, py_strict_lines, py_strict_err = ir_disasm_source_captured(args.file, strict=True, engine="python")
                        _src_w2, sh_strict_ok, sh_strict_lines, sh_strict_err = ir_disasm_source_captured(args.file, strict=True, engine="selfhost")
                        payload["strict_warning_match"] = (
                            py_strict_ok == sh_strict_ok
                            and py_strict_lines == sh_strict_lines
                            and py_strict_err == sh_strict_err
                        )
                        payload["python_strict_ok"] = py_strict_ok
                        payload["python_strict_error"] = py_strict_err
                        payload["selfhost_strict_ok"] = sh_strict_ok
                        payload["selfhost_strict_error"] = sh_strict_err
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Kilde: {source_path}")
                    print("Motor: diff (python vs selfhost)")
                    if py_lines == sh_lines:
                        print("IR disasm: MATCH")
                        for line in py_lines:
                            print(line)
                    else:
                        print("IR disasm: MISMATCH")
                        diff_lines = list(difflib.unified_diff(
                            py_lines,
                            sh_lines,
                            fromfile="python",
                            tofile="selfhost",
                            lineterm="",
                        ))
                        for line in diff_lines:
                            print(line)
                        if args.save_diff:
                            save_path = Path(args.save_diff).expanduser()
                            save_path.write_text("\n".join(diff_lines) + "\n", encoding="utf-8")
                            print(f"Diff lagret: {save_path.resolve()}")
                        sys.exit(1)

                    if args.fail_on_warning:
                        _src_w1, py_strict_ok, py_strict_lines, py_strict_err = ir_disasm_source_captured(args.file, strict=True, engine="python")
                        _src_w2, sh_strict_ok, sh_strict_lines, sh_strict_err = ir_disasm_source_captured(args.file, strict=True, engine="selfhost")
                        warning_match = (
                            py_strict_ok == sh_strict_ok
                            and py_strict_lines == sh_strict_lines
                            and py_strict_err == sh_strict_err
                        )
                        if warning_match:
                            print("Warning check: MATCH")
                        else:
                            print("Warning check: MISMATCH")
                            print(f"python strict: {'OK' if py_strict_ok else py_strict_err}")
                            print(f"selfhost strict: {'OK' if sh_strict_ok else sh_strict_err}")
                            if args.save_diff:
                                diff_text = (
                                    "Warning check mismatch\n"
                                    f"python strict: {'OK' if py_strict_ok else py_strict_err}\n"
                                    f"selfhost strict: {'OK' if sh_strict_ok else sh_strict_err}\n"
                                )
                                save_path = Path(args.save_diff).expanduser()
                                save_path.write_text(diff_text, encoding="utf-8")
                                print(f"Diff lagret: {save_path.resolve()}")
                            sys.exit(1)
            else:
                source_path, lines = ir_disasm_source(args.file, strict=args.strict, engine=args.engine)
                if args.json:
                    payload = {
                        "source": str(source_path),
                        "engine": args.engine,
                        "lines": lines,
                    }
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"Kilde: {source_path}")
                    print(f"Motor: {args.engine}")
                    print("IR disasm:")
                    for line in lines:
                        print(line)

        elif args.cmd == "update-snapshots":
            fixture_path, updated, total = update_ir_snapshots(check_only=args.check)
            print(f"Oppdatert snapshot-fixture: {fixture_path}")
            print(f"Strict-cases: {total}")
            if args.check:
                print(f"Avvik funnet: {updated}")
                if updated > 0:
                    sys.exit(1)
            else:
                print(f"Endringer skrevet: {updated}")

        elif args.cmd == "test":
            if args.file:
                result = run_test_file(args.file)
                print_test_result(result, verbose=args.verbose)
                if not result["success"]:
                    sys.exit(1)
            else:
                results = run_all_tests(verbose=args.verbose)
                if any(not r["success"] for r in results):
                    sys.exit(1)

        else:
            parser.print_help()
            sys.exit(1)

    except Exception as e:
        print(f"Feil: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
