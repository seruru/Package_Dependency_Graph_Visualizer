import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Инструмент визуализации графа зависимостей пакетов (этап 1)"
    )

    parser.add_argument(
        "--package",
        type=str,
        required=True,
        help="Имя анализируемого пакета"
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="URL-адрес репозитория или путь к файлу тестового репозитория"
    )
    parser.add_argument(
        "--test-mode",
        type=str,
        choices=["true", "false"],
        required=True,
        help="Режим работы с тестовым репозиторием (true/false)"
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Версия пакета"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="graph.png",
        help="Имя сгенерированного файла с изображением графа"
    )
    parser.add_argument(
        "--ascii-tree",
        type=str,
        choices=["true", "false"],
        default="false",
        help="Режим вывода зависимостей в формате ASCII-дерева (true/false)"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Максимальная глубина анализа зависимостей"
    )

    args = parser.parse_args()

    print("Настроенные параметры:")
    print(f"  Пакет: {args.package}")
    print(f"  Репозиторий: {args.repo}")
    print(f"  Тестовый режим: {args.test_mode}")
    print(f"  Версия: {args.version}")
    print(f"  Выходной файл: {args.output}")
    print(f"  ASCII-дерево: {args.ascii_tree}")
    print(f"  Максимальная глубина: {args.max_depth}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)