from pathlib import Path

from .ast_nodes import ProgramNode
from .lexer import Lexer
from .parser import Parser


class ModuleLoader:
    def __init__(self, root):
        self.root = Path(root)
        self.loaded = {}
        self.loading = set()

    def parse_file(self, file_path: Path):
        source = file_path.read_text(encoding="utf-8")
        lexer = Lexer(source)
        parser = Parser(lexer)
        return parser.parse()

    def _set_module_name(self, program, module_name):
        for fn in getattr(program, "functions", []):
            fn.module_name = module_name

    def _merge_programs(self, programs):
        all_functions = []
        for program in programs:
            all_functions.extend(getattr(program, "functions", []))
        return ProgramNode([], all_functions)

    def _module_candidates(self, module_name: str):
        rel_path = Path(*module_name.split(".")).with_suffix(".no")
        dot_path = Path(f"{module_name}.no")

        candidates = []
        seen = set()
        for base in (self.root, *self.root.parents):
            for path in (base / dot_path, base / rel_path):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                candidates.append(path)
        return candidates

    def load_module(self, module_name: str):
        if module_name in self.loaded:
            return self.loaded[module_name]

        if module_name in self.loading:
            raise RuntimeError(f"Sirkulær import oppdaget: {module_name}")

        self.loading.add(module_name)
        try:
            candidates = self._module_candidates(module_name)

            file_path = None
            for candidate in candidates:
                if candidate.exists():
                    file_path = candidate
                    break

            if file_path is None:
                searched = "\n".join(str(p) for p in candidates)
                raise RuntimeError(f"Fant ikke modulfil for '{module_name}'. Søkte i:\n{searched}")

            program = self.parse_file(file_path)
            self._set_module_name(program, module_name)

            imported_programs = []
            for imp in getattr(program, "imports", []):
                imported_programs.append(self.load_module(imp.module_name))

            merged = self._merge_programs([*imported_programs, program])
            self.loaded[module_name] = merged
            return merged
        finally:
            self.loading.discard(module_name)

    def load_entry_file(self, name):
        entry_path = self.root / name
        if not entry_path.exists():
            raise RuntimeError(f"Fant ikke inngangsfil: {entry_path}")

        program = self.parse_file(entry_path)
        self._set_module_name(program, "__main__")

        alias_map = {}
        imported_programs = []

        for imp in getattr(program, "imports", []):
            imported_programs.append(self.load_module(imp.module_name))
            alias_name = getattr(imp, "alias", None) or imp.module_name.split(".")[-1]
            if alias_name in alias_map:
                raise RuntimeError(f"Alias brukt flere ganger: {alias_name}")
            alias_map[alias_name] = imp.module_name

        merged = self._merge_programs([*imported_programs, program])
        return merged, alias_map
