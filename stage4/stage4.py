#!/usr/bin/env python3
import argparse
import sys
import json
import urllib.request
import subprocess
import os

sys.setrecursionlimit(10000)


class DependencyGraph:
    def __init__(self):
        self.graph = {}
        self.seen = set()
        self.cycle_detected = False
        self.cycle_edges = set()

    def fetch_package_data(self, pkg):
        url = f"https://registry.npmjs.org/{pkg}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except Exception:
            return None

    def clean_version(self, ver):
        import re
        if not ver:
            return ver
        return re.sub(r"^[\^~<>=\s]*", "", ver)

    def get_direct_dependencies(self, pkg, ver):
        data = self.fetch_package_data(pkg)
        if not data:
            return {}
        versions = data.get("versions", {})
        if ver in versions:
            return versions[ver].get("dependencies", {}) or {}
        cleaned = self.clean_version(ver or "")
        if cleaned in versions:
            return versions[cleaned].get("dependencies", {}) or {}
        dist_tags = data.get("dist-tags", {})
        latest = dist_tags.get("latest")
        if latest and latest in versions:
            return versions[latest].get("dependencies", {}) or {}
        return {}

    def build_graph_from_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or ":" not in line:
                        continue
                    left, right = line.split(":", 1)
                    key = left.strip()
                    deps = [p.strip() for p in right.replace(",", " ").split() if p.strip()]
                    self.graph[key] = deps
            return True
        except Exception:
            return False

    def build_dependency_graph_test(self, root_pkg, max_depth):
        self.seen = set()
        self.cycle_detected = False
        self.cycle_edges = set()
        visiting = set()
        finished = set()

        def dfs(pkg, depth, path):
            if depth > max_depth:
                return
            self.seen.add(pkg)
            if pkg in visiting:
                self.cycle_detected = True
                if path:
                    self.cycle_edges.add((path[-1], pkg))
                return
            if pkg in finished:
                return
            visiting.add(pkg)
            children = self.graph.get(pkg, [])
            for child in children:
                if child in visiting:
                    self.cycle_detected = True
                    self.cycle_edges.add((pkg, child))
                    continue
                dfs(child, depth + 1, path + [child])
            visiting.remove(pkg)
            finished.add(pkg)

        dfs(root_pkg, 0, [root_pkg])

    def build_dependency_graph_real(self, root_pkg, root_ver, max_depth):
        self.seen = set()
        self.cycle_detected = False
        self.cycle_edges = set()
        visiting = set()
        finished = set()

        def dfs(pkg, ver, depth, path):
            if depth > max_depth:
                return
            self.seen.add(pkg)
            if pkg in visiting:
                self.cycle_detected = True
                if path:
                    self.cycle_edges.add((path[-1], pkg))
                return
            if pkg in finished:
                return
            visiting.add(pkg)
            deps = self.get_direct_dependencies(pkg, ver)
            self.graph[pkg] = list(deps.keys())
            for dep_name, dep_ver in deps.items():
                dep_clean = self.clean_version(dep_ver)
                if dep_name in visiting:
                    self.cycle_detected = True
                    self.cycle_edges.add((pkg, dep_name))
                    continue
                dfs(dep_name, dep_clean, depth + 1, path + [dep_name])
            visiting.remove(pkg)
            finished.add(pkg)

        dfs(root_pkg, root_ver, 0, [root_pkg])

    def print_ascii_tree(self, root):
        def rec(node, prefix, is_last, path_set):
            cyc = ""
            if node in path_set:
                cyc = " [CYCLE]"
                print(prefix + ("└── " if is_last else "├── ") + node + cyc)
                return
            print(prefix + ("└── " if is_last else "├── ") + node + cyc)
            children = self.graph.get(node, [])
            if not children:
                return
            new_prefix = prefix + ("    " if is_last else "│   ")
            for i, child in enumerate(children):
                rec(child, new_prefix, i == len(children) - 1, path_set | {node})

        if root not in self.graph and root not in self.seen:
            print(f"(нет информации о пакете {root})")
            return
        rec(root, "", True, set())

    def get_dependency_order(self):
        if self.cycle_detected:
            return []
        nodes = set(self.seen)
        for k, kids in self.graph.items():
            nodes.add(k)
            for c in kids:
                nodes.add(c)
        indeg = {n: 0 for n in nodes}
        for n in nodes:
            for nb in self.graph.get(n, []):
                if nb in indeg:
                    indeg[nb] += 1
        from collections import deque
        q = deque([n for n in nodes if indeg[n] == 0])
        order = []
        while q:
            n = q.popleft()
            order.append(n)
            for nb in self.graph.get(n, []):
                if nb in indeg:
                    indeg[nb] -= 1
                    if indeg[nb] == 0:
                        q.append(nb)
        return order

    def npm_load_order(self, root):
        seen = set()
        order = []

        def dfs(pkg):
            if pkg in seen:
                return
            seen.add(pkg)
            for child in self.graph.get(pkg, []):
                dfs(child)
            order.append(pkg)

        dfs(root)
        return order[::-1]


def parse_npm_ls_json(npm_json, root_name):
    order = []
    seen = set()

    def rec(node_name, node_obj):
        if node_name in seen:
            return
        seen.add(node_name)
        deps = node_obj.get("dependencies", {}) if isinstance(node_obj, dict) else {}
        for child_name, child_obj in deps.items():
            rec(child_name, child_obj)
        order.append(node_name)

    if not isinstance(npm_json, dict):
        return []
    top = npm_json.get("dependencies", {})
    if root_name in top:
        rec(root_name, top[root_name])
    else:
        # if root not under dependencies, try traverse entire tree
        for name, obj in top.items():
            rec(name, obj)
    return order[::-1]


def run_npm_ls(package, max_depth):
    try:
        cmd = ["npm", "ls", package, "--json", f"--depth={max_depth}"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 and not proc.stdout:
            return None, proc.stderr.strip()
        out = proc.stdout.strip()
        if not out:
            return None, proc.stderr.strip()
        try:
            data = json.loads(out)
            return data, None
        except Exception as e:
            return None, f"Ошибка разбора JSON от npm: {e}"
    except FileNotFoundError:
        return None, "npm не найден в PATH"
    except Exception as e:
        return None, str(e)


def compare_orders(our_order, npm_order):
    set_our = list(dict.fromkeys(our_order))
    set_npm = list(dict.fromkeys(npm_order))
    only_our = [x for x in set_our if x not in set_npm]
    only_npm = [x for x in set_npm if x not in set_our]
    pos_diff = []
    positions = {}
    for i, p in enumerate(set_npm):
        positions[p] = i
    for i, p in enumerate(set_our):
        if p in positions:
            pos_diff.append((p, i, positions[p]))
    return {"only_our": only_our, "only_npm": only_npm, "pos_diff": pos_diff}


def main():
    parser = argparse.ArgumentParser(description="Stage 4: dependency load order and comparison")
    parser.add_argument("--package", required=True, help="root package name")
    parser.add_argument("--url", required=True, help="repo URL or test file path")
    parser.add_argument("--mode", choices=["real", "test"], required=True, help="mode: real or test")
    parser.add_argument("--version", help="version required in real mode")
    parser.add_argument("--ascii", action="store_true", help="print ASCII tree")
    parser.add_argument("--max-depth", type=int, default=10, help="max depth")
    parser.add_argument("--load-order", action="store_true", help="print npm-style load order")
    parser.add_argument("--compare-npm", action="store_true", help="try to run npm ls and compare orders")
    args = parser.parse_args()

    dg = DependencyGraph()

    if args.mode == "test":
        ok = dg.build_graph_from_file(args.url)
        if not ok:
            print("Ошибка: не удалось прочитать тестовый файл.")
            sys.exit(1)
        if args.package not in dg.graph:
            print("Ошибка: корневой пакет не найден в тестовом файле.")
            sys.exit(1)
        direct = dg.graph.get(args.package, [])
        print(f"Direct dependencies of {args.package}: {direct if direct else '(none)'}")
        dg.build_dependency_graph_test(args.package, args.max_depth)
        print(f"Graph built for {args.package} (test). Nodes in file: {len(dg.graph)}. Reachable: {len(dg.seen)}.")
    else:
        if not args.version:
            print("Error: --version is required in real mode")
            sys.exit(1)
        direct = dg.get_direct_dependencies(args.package, args.version)
        if direct:
            print(f"Direct dependencies of {args.package}@{args.version}:")
            for k, v in direct.items():
                print(f"  - {k}: {v}")
        else:
            print(f"Direct dependencies of {args.package}@{args.version}: (none or unavailable)")
        dg.build_dependency_graph_real(args.package, args.version, args.max_depth)
        print(f"Graph built for {args.package}@{args.version} (real). Nodes: {len(dg.graph)}.")

    if dg.cycle_detected:
        print("Cyclic dependencies detected!")

    if args.ascii:
        print("\nASCII dependency tree:")
        dg.print_ascii_tree(args.package)
        print()

    if args.load_order:
        order = dg.npm_load_order(args.package)
        if order:
            print("NPM-style load order:")
            for i, p in enumerate(order, 1):
                print(f"{i}. {p}")
        else:
            print("NPM-style load order: (empty or cannot determine due to cycles)")

    topo = dg.get_dependency_order()
    if topo:
        print("\nTopological order (Kahn):")
        for i, p in enumerate(topo, 1):
            print(f"{i}. {p}")
    else:
        if dg.cycle_detected:
            print("\nTopological order not available due to cycles.")
        else:
            print("\nTopological order: (none)")

    if args.compare_npm:
        print("\nAttempting to run `npm ls` to compare orders...")
        npm_json, npm_err = run_npm_ls(args.package, args.max_depth)
        if npm_err:
            print(f"Could not run npm or parse result: {npm_err}")
        elif npm_json is None:
            print("npm returned no JSON output.")
        else:
            npm_order = parse_npm_ls_json(npm_json, args.package)
            our_order = dg.npm_load_order(args.package)
            print("\nOur NPM-style order (count {}):".format(len(our_order)))
            for i, p in enumerate(our_order, 1):
                print(f"  {i}. {p}")
            print("\nnpm ls derived order (count {}):".format(len(npm_order)))
            for i, p in enumerate(npm_order, 1):
                print(f"  {i}. {p}")
            comp = compare_orders(our_order, npm_order)
            if comp["only_our"]:
                print("\nPackages present only in our order:", ", ".join(comp["only_our"]))
            if comp["only_npm"]:
                print("Packages present only in npm's order:", ", ".join(comp["only_npm"]))
            if comp["pos_diff"]:
                print("\nPosition differences (package, our_pos, npm_pos):")
                for p, o_pos, n_pos in comp["pos_diff"]:
                    print(f"  {p}: our {o_pos} vs npm {n_pos}")
            if not comp["only_our"] and not comp["only_npm"]:
                print("\nOrders contain same package set (positions may differ).")
            print("\nNote: npm resolves specific versions, peer/recommended deps and installs nested node_modules. Differences in order may arise from version resolution, pruning, optional/peer deps or npm's internal install strategy.")

    print("\nDone.")


if __name__ == "__main__":
    main()
