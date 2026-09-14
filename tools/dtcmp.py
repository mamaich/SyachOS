#!/usr/bin/env python3
"""Структурное сравнение двух DTB, устойчивое к перенумерации phandle.

Сравнивает: множество путей узлов, множество имён свойств в каждом узле
и значения тех свойств, где нет ссылок (строки, булевы, простые числа).
Значения со ссылками не сравниваются - их номера сдвигаются при добавлении
узлов, и проверять их надо адресно.
"""
import re, subprocess, sys

def load(dtb):
    dts = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", dtb],
                         capture_output=True, text=True).stdout
    tree, path = {}, []
    for raw in dts.split("\n"):
        line = raw.strip()
        if not line or line.startswith(("/dts-v1/", "//", "/memreserve/")):
            continue
        if line.endswith("{"):
            path.append(line[:-1].strip()); tree.setdefault("/".join(path), {})
        elif line == "};":
            if path: path.pop()
        elif line.endswith(";"):
            body = line[:-1]
            if "=" in body:
                k, v = body.split("=", 1); tree.setdefault("/".join(path), {})[k.strip()] = v.strip()
            else:
                tree.setdefault("/".join(path), {})[body.strip()] = True
    return tree

A, B = load(sys.argv[1]), load(sys.argv[2])
print("узлов: %d и %d" % (len(A), len(B)))

oa, ob = sorted(set(A) - set(B)), sorted(set(B) - set(A))
print("\n--- узлы только в первом (%d):" % len(oa));  [print("   ", x) for x in oa[:15]]
print("--- узлы только во втором (%d):" % len(ob));   [print("   ", x) for x in ob[:15]]

print("\n--- узлы с разным НАБОРОМ свойств:")
n = 0
for p in sorted(set(A) & set(B)):
    if p.endswith("__symbols__"): continue
    ka, kb = set(A[p]) - {"phandle"}, set(B[p]) - {"phandle"}
    if ka != kb:
        n += 1
        if n <= 20:
            print("  %s" % p)
            if ka - kb: print("      только в первом:  %s" % ", ".join(sorted(ka - kb)))
            if kb - ka: print("      только во втором: %s" % ", ".join(sorted(kb - ka)))
print("  всего таких узлов: %d" % n)

print("\n--- различия значений (только свойства без ссылок):")
m = 0
for p in sorted(set(A) & set(B)):
    if p.endswith("__symbols__"): continue
    for k in sorted((set(A[p]) & set(B[p])) - {"phandle"}):
        va, vb = A[p][k], B[p][k]
        if va == vb: continue
        if isinstance(va, str) and "<" in va:      # есть ячейки - могут быть ссылки
            cells = re.findall(r"0x[0-9a-f]+", va) + re.findall(r"0x[0-9a-f]+", str(vb))
            if cells: continue
        m += 1
        if m <= 20: print("  %s :: %s\n      %s\n      %s" % (p, k, va, vb))
print("  всего: %d" % m)
