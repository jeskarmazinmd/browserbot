import ast
from pathlib import Path

TARGET = Path("quote_source_extracted.py")

tree = ast.parse(TARGET.read_text())

defined = set()
used = set()
imports = set()

class Analyzer(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        defined.add(node.name)

        for arg in node.args.args:
            defined.add(arg.arg)

        for arg in node.args.kwonlyargs:
            defined.add(arg.arg)

        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            defined.add(node.name)

        self.generic_visit(node)

    def visit_ClassDef(self, node):
        defined.add(node.name)
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            imports.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node):
        for alias in node.names:
            imports.add(alias.asname or alias.name)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            defined.add(node.id)


Analyzer().visit(tree)

builtins = set(dir(__builtins__))

missing = sorted(
    used
    - defined
    - imports
    - builtins
)

print("\nDEFINED:")
for x in sorted(defined):
    print(" ", x)

print("\nIMPORTS:")
for x in sorted(imports):
    print(" ", x)

print("\nMISSING:")
for x in missing:
    print(" ", x)

if not missing:
    print("\n✓ No missing dependencies")
else:
    print(f"\nFound {len(missing)} missing dependencies")
