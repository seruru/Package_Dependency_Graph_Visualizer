import argparse
import sys
import json
import urllib.request
from urllib.error import URLError, HTTPError

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
                data = resp.read().decode('utf-8')
                return json.loads(data)
        except Exception:
            return None

    def clean_version(self, ver):
        import re
        if not ver:
            return ver
        return re.sub(r'^[\^~<>=\s]*', '', ver)

    def get_direct_dependencies(self, pkg, ver):
        data = self.fetch_package_data(pkg)
        if not data:
            return {}

        versions = data.get('versions', {})
        if ver in versions:
            return versions[ver].get('dependencies', {}) or {}

        cleaned = self.clean_version(ver or "")
        if cleaned in versions:
            return versions[cleaned].get('dependencies', {}) or {}

        dist_tags = data.get('dist-tags', {})
        latest = dist_tags.get('latest')
        if latest and latest in versions:
            return versions[latest].get('dependencies', {}) or {}

        return {}

    def build_graph_from_file(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or ':' not in line:
                        continue
                    left, right = line.split(':', 1)
                    key = left.strip()
                    deps = [p.strip() for p in right.replace(',', ' ').split() if p.strip()]
                    self.graph[key] = deps
            return True
        except Exception:
            return False

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
                if len(path) >= 1:
                    parent = path[-1]
                    self.cycle_edges.add((parent, pkg))
                return
            if pkg in finished:
                return

            visiting.add(pkg)
            deps = self.get_direct_dependencies(pkg, ver)
            self.graph[pkg] = list(deps.keys())

            for dep_name, dep_ver in deps.items():
                dep_ver_clean = self.clean_version(dep_ver)
                if dep_name in visiting:
                    self.cycle_detected = True
                    self.cycle_edges.add((pkg, dep_name))
                    continue
                dfs(dep_name, dep_ver_clean, depth + 1, path + [dep_name])

            visiting.remove(pkg)
            finished.add(pkg)

        dfs(root_pkg, root_ver, 0, [root_pkg])

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
                if len(path) >= 1:
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

    def print_ascii_tree(self, root):
        def rec(node, prefix, is_last, path_set):
            cycle_mark = ""
            if node in path_set:
                cycle_mark = " [CYCLE]"
                print(prefix + ("└── " if is_last else "├── ") + node + cycle_mark)
                return

            print(prefix + ("└── " if is_last else "├── ") + node + cycle_mark)
            children = self.graph.get(node, [])
            if not children:
                return

            new_prefix = prefix + ("    " if is_last else "│   ")
            for i, child in enumerate(children):
                last = (i == len(children) - 1)
                rec(child, new_prefix, last, path_set | {node})

        rec(root, "", True, set())

    def get_dependency_order(self):
        if self.cycle_detected:
            return []

        nodes = set(self.seen)
        for k, kids in self.graph.items():
            nodes.add(k)
            for c in kids:
                nodes.add(c)

        in_degree = {n: 0 for n in nodes}
        for n in nodes:
            for nb in self.graph.get(n, []):
                if nb in in_degree:
                    in_degree[nb] += 1

        from collections import deque
        q = deque([n for n in nodes if in_degree[n] == 0])

        order = []
        while q:
            n = q.popleft()
            order.append(n)
            for nb in self.graph.get(n, []):
                if nb in in_degree:
                    in_degree[nb] -= 1
                    if in_degree[nb] == 0:
                        q.append(nb)

        return order


def main():
    parser = argparse.ArgumentParser(description="Dependency graph tool")
    parser.add_argument("--package", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--mode", choices=["real", "test"], required=True)
    parser.add_argument("--version")
    parser.add_argument("--output", default="graph.png")
    parser.add_argument("--ascii", action="store_true")
    parser.add_argument("--max-depth", type=int, default=10)

    args = parser.parse_args()

    print("\nПараметры:")
    for k, v in vars(args).items():
        print(f"  {k}: {v}")
    print()

    dg = DependencyGraph()

    if args.mode == "test":
        ok = dg.build_graph_from_file(args.url)
        if not ok:
            print("Ошибка чтения файла.")
            sys.exit(1)

        if args.package not in dg.graph:
            print("Корневой пакет не найден в тестовом файле.")
            sys.exit(1)

        direct = dg.graph.get(args.package, [])
        print(f"Прямые зависимости {args.package}: {direct}\n")

        dg.build_dependency_graph_test(args.package, args.max_depth)

        print(f"Построен граф для {args.package}.\n")
        if args.ascii:
            dg.print_ascii_tree(args.package)
            print()

        print("Порядок загрузки:")
        order = dg.get_dependency_order()
        for i, p in enumerate(order, 1):
            print(f"{i}. {p}")

    else:
        if not args.version:
            print("Нужен параметр --version")
            sys.exit(1)

        direct = dg.get_direct_dependencies(args.package, args.version)
        print(f"Прямые зависимости {args.package}: {direct}\n")

        dg.build_dependency_graph_real(args.package, args.version, args.max_depth)

        print(f"Построен граф для {args.package}.\n")
        if args.ascii:
            dg.print_ascii_tree(args.package)
            print()

        print("Порядок загрузки:")
        order = dg.get_dependency_order()
        for i, p in enumerate(order, 1):
            print(f"{i}. {p}")


if __name__ == "__main__":
    main()
