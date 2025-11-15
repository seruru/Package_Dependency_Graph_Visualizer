#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
import json
import urllib.request
from urllib.error import URLError, HTTPError

# Увеличим лимит рекурсии, если глубина большая
sys.setrecursionlimit(10000)


class DependencyGraph:
    def __init__(self):
        # словарь графа: ключ = пакет, значение = список зависимостей (имен)
        self.graph = {}
        # все обнаруженные узлы (достижимые из корня)
        self.seen = set()
        # признак обнаружения цикла
        self.cycle_detected = False
        # набор ребер, которые являются частью цикла (для вывода)
        self.cycle_edges = set()
        # вспомогательное поле для отладки/логов
        self.logs = []

    # -------------------- работа с npm registry --------------------
    def fetch_package_data(self, pkg):
        """
        Получить JSON-представление пакета из registry.npmjs.org.
        Возвращает dict или None при ошибке.
        """
        url = f"https://registry.npmjs.org/{pkg}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = resp.read().decode('utf-8')
                return json.loads(data)
        except HTTPError as e:
            print(f"HTTP Error при получении {pkg}: {e.code} {e.reason}")
        except URLError as e:
            print(f"URL Error при получении {pkg}: {e.reason}")
        except Exception as e:
            print(f"Ошибка при получении {pkg}: {e}")
        return None

    def clean_version(self, ver):
        """Убираем ведущие символы ^ ~ >= <= и т.п."""
        import re
        if not ver:
            return ver
        return re.sub(r'^[\^~<>=\s]*', '', ver)

    def get_direct_dependencies(self, pkg, ver):
        """
        Возвращает dict прямых зависимостей для pkg@ver.
        Если версии нет — пытаемся использовать очищённую версию или 'latest'.
        """
        data = self.fetch_package_data(pkg)
        if not data:
            return {}

        versions = data.get('versions', {})
        # 1) если точная версия есть - используем
        if ver in versions:
            return versions[ver].get('dependencies', {}) or {}

        # 2) попробуем очистить версию (удалить ^~ и т.д.)
        cleaned = self.clean_version(ver or "")
        if cleaned and cleaned in versions:
            return versions[cleaned].get('dependencies', {}) or {}

        # 3) попробуем взять dist-tags.latest
        dist_tags = data.get('dist-tags', {})
        latest = dist_tags.get('latest')
        if latest and latest in versions:
            # сообщим пользователю, что используем latest как fallback
            print(f"Предупреждение: версия '{ver}' не найдена для {pkg}. Использую latest -> {latest}")
            return versions[latest].get('dependencies', {}) or {}

        # 4) иначе — возвращаем пустой набор и сообщаем
        print(f"Версия '{ver}' не найдена для {pkg} и fallback не сработал.")
        return {}

    # -------------------- чтение тестового файла --------------------
    def build_graph_from_file(self, path):
        """
        Ожидаемый формат файла (каждая строка):
        A: B C D
        B: C E
        C:
        Пакеты и зависимости разделены пробелами. Пропускаются пустые строки.
        Возвращает True если файл прочитан успешно.
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or ':' not in line:
                        continue
                    left, right = line.split(':', 1)
                    key = left.strip()
                    # допускаем запятые или пробелы как разделители
                    deps = [p.strip() for p in right.replace(',', ' ').split() if p.strip()]
                    self.graph[key] = deps
            return True
        except Exception as e:
            print(f"Ошибка чтения файла {path}: {e}")
            return False

    # -------------------- DFS (рекурсивный) для реального npm --------------------
    def build_dependency_graph_real(self, root_pkg, root_ver, max_depth):
        """
        Построение графа для реального репозитория через рекурсивный DFS.
        max_depth - максимальная глубина (0 = только корень).
        """
        self.seen = set()
        self.cycle_detected = False
        self.cycle_edges = set()

        # вспомогательные множества для DFS
        visiting = set()   # текущий рекурсивный стек (для обнаружения циклов)
        finished = set()   # уже полностью обработанные узлы

        def dfs(pkg, ver, depth, path):
            # depth - текущая глубина (root = 0)
            if depth > max_depth:
                return
            # пометим как обнаруженный (включается в итоговую область видимости)
            self.seen.add(pkg)

            if pkg in visiting:
                # цикл: пакет снова в стеке
                self.cycle_detected = True
                # отмечаем ребро (предок -> pkg) как циклическое
                if len(path) >= 1:
                    parent = path[-1]
                    self.cycle_edges.add((parent, pkg))
                return

            if pkg in finished:
                # уже полностью обработан ранее
                return

            visiting.add(pkg)
            # получаем зависимости данного пакета
            deps = self.get_direct_dependencies(pkg, ver)
            # гарантируем, что даже пакет без зависимостей присутствует в словаре
            self.graph[pkg] = list(deps.keys())

            # для каждой зависимости рекурсивно вызываем DFS
            for dep_name, dep_ver in deps.items():
                # чистим версию (удаляем ^~ и т.д.)
                dep_ver_clean = self.clean_version(dep_ver)
                # если зависимость уже в текущем пути -> цикл
                if dep_name in visiting:
                    self.cycle_detected = True
                    self.cycle_edges.add((pkg, dep_name))
                    # не спускаться дальше по этой ветке
                    continue
                # рекурсивный вызов
                dfs(dep_name, dep_ver_clean, depth + 1, path + [dep_name])

            # пометить как завершённый
            visiting.remove(pkg)
            finished.add(pkg)

        dfs(root_pkg, root_ver, 0, [root_pkg])

    # -------------------- DFS (рекурсивный) для тестового файла --------------------
    def build_dependency_graph_test(self, root_pkg, max_depth):
        """
        Построение графа из self.graph (который уже загружен из файла)
        с использованием рекурсивного DFS.
        """
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

    # -------------------- вывод ASCII-дерева --------------------
    def print_ascii_tree(self, root):
        """
        Рекурсивный вывод дерева зависимостей.
        Помечает узлы, попавшие в цикл.
        """
        visited_path = set()

        def rec(node, prefix, is_last, path_set):
            # если узел уже в текущем пути -> цикл
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
            # итерация по порядку (не забудем, что последний рисуется как '└──')
            for i, child in enumerate(children):
                last = (i == len(children) - 1)
                rec(child, new_prefix, last, path_set | {node})

        # старт
        if root not in self.graph and root not in self.seen:
            print(f"(нет информации о пакете {root})")
            return
        rec(root, "", True, set())

    # -------------------- порядок загрузки (topological order) --------------------
    def get_dependency_order(self):
        """
        Возвращает порядок установки (топологическая сортировка Kahn) для
        узлов, достижимых из root (self.seen).
        Если есть цикл — возвращает [] и выводит предупреждение.
        """
        if self.cycle_detected:
            print("Невозможно определить порядок установки из-за циклических зависимостей.")
            return []

        # формируем множество всех узлов, которые нужно учитывать:
        nodes = set(self.seen)
        # также добавляем зависимости, которые могут быть упомянуты, но не ключи self.graph
        for k, kids in self.graph.items():
            nodes.add(k)
            for c in kids:
                nodes.add(c)

        # вычисляем in-degree
        in_degree = {n: 0 for n in nodes}
        for n in nodes:
            for nb in self.graph.get(n, []):
                if nb in in_degree:
                    in_degree[nb] += 1

        # очередь стартовых узлов
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

        if len(order) != len(nodes):
            print("Внимание: не все узлы упорядочены (возможен цикл).")

        return order


# -------------------- CLI и запуск --------------------
def main():
    parser = argparse.ArgumentParser(description="Инструмент визуализации графа зависимостей (Этап 3)")
    parser.add_argument("--package", required=True, help="Имя анализируемого пакета (root)")
    parser.add_argument("--url", required=True, help="URL репозитория или путь к тестовому файлу")
    parser.add_argument("--mode", choices=["real", "test"], required=True, help="Режим: real или test")
    parser.add_argument("--version", help="Версия пакета (требуется в режиме real), пример 1.2.3")
    parser.add_argument("--output", default="graph.png", help="Имя выходного файла (будет использовано на этапе визуализации)")
    parser.add_argument("--ascii", action="store_true", help="Вывод зависимостей в виде ASCII-дерева")
    parser.add_argument("--max-depth", type=int, default=10, help="Максимальная глубина анализа (0 = только корень)")

    args = parser.parse_args()

    # выводим ключ-значение (требование этапа 1/навигация)
    print("\nПараметры:")
    for k, v in vars(args).items():
        print(f"  {k}: {v}")
    print()

    dg = DependencyGraph()

    if args.mode == "test":
        # проверяем чтение файла
        ok = dg.build_graph_from_file(args.url)
        if not ok:
            print("Ошибка: не удалось прочитать тестовый файл.")
            sys.exit(1)

        # проверка наличия корня в файле
        if args.package not in dg.graph:
            print(f"Ошибка: пакет {args.package} не найден в тестовом файле.")
            sys.exit(1)

        # показываем прямые зависимости корня
        direct = dg.graph.get(args.package, [])
        print(f"Прямые зависимости {args.package}: {direct if direct else '(нет)'}\n")

        # строим граф DFS рекурсией
        dg.build_dependency_graph_test(args.package, args.max_depth)

        print(f"Построен граф зависимостей для {args.package} (тестовый режим).")
        print(f"Всего пакетов в файле: {len(dg.graph)}")
        print(f"Достижимых пакетов из {args.package}: {len(dg.seen)}")
        if dg.cycle_detected:
            print("Обнаружены циклические зависимости!")
        print()

        if args.ascii:
            print("ASCII-дерево:")
            dg.print_ascii_tree(args.package)
            print()

        print("Порядок загрузки (если возможен):")
        order = dg.get_dependency_order()
        if order:
            for i, p in enumerate(order, 1):
                print(f"  {i}. {p}")
        print()

    else:  # real mode
        if not args.version:
            print("Ошибка: параметр --version обязателен в режиме real.")
            sys.exit(1)

        # показываем прямые зависимости корня (этап 2)
        direct = dg.get_direct_dependencies(args.package, args.version)
        if direct:
            print(f"Прямые зависимости {args.package}@{args.version}:")
            for k, vv in direct.items():
                print(f"  - {k}: {vv}")
            print()
        else:
            print(f"Прямых зависимостей не обнаружено или не удалось получить информацию для {args.package}@{args.version}\n")

        # строим граф рекурсивно DFS
        dg.build_dependency_graph_real(args.package, args.version, args.max_depth)

        print(f"Построен граф зависимостей для {args.package}@{args.version} (real).")
        print(f"Всего узлов в графе (ключей): {len(dg.graph)}")
        if dg.cycle_detected:
            print("Обнаружены циклические зависимости!")
        print()

        if args.ascii:
            print("ASCII-дерево:")
            dg.print_ascii_tree(args.package)
            print()

        print("Порядок загрузки (если возможен):")
        order = dg.get_dependency_order()
        if order:
            for i, p in enumerate(order, 1):
                print(f"  {i}. {p}")
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)
