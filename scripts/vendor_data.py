"""Copy data/ and SKILL.md into the package so the wheel is self-contained. Run before `python -m build`.
Never commit the copy; .gitignore excludes it. The installed package's dataset_digest() must equal the
repo's, which is what tests/test_packaging.py asserts after a wheel install."""
import os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src, dst = os.path.join(ROOT, "data"), os.path.join(ROOT, "src", "marina_rules", "data")
if os.path.isdir(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
n = sum(len(f) for _, _, f in os.walk(dst))
print(f"vendored {n} files into {os.path.relpath(dst, ROOT)}")
# the usage notes travel with the wheel too (marina_rules.skill_text()); same rule: a copy, never committed
shutil.copyfile(os.path.join(ROOT, "SKILL.md"), os.path.join(ROOT, "src", "marina_rules", "SKILL.md"))
print("vendored SKILL.md into src/marina_rules")
