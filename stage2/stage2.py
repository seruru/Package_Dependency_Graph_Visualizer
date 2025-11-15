import argparse
import sys
import urllib.request
import json
from urllib.error import URLError, HTTPError

def get_package_info(package_name, repo_url, version):
    """
    Получает информацию о пакете из npm репозитория
    """
    try:
        # Формируем URL для запроса информации о пакете
        if repo_url.endswith('/'):
            repo_url = repo_url[:-1]
        
        url = f"{repo_url}/{package_name}/{version}"
        
        print(f"Запрос данных из: {url}")
        
        # Выполняем HTTP запрос
        with urllib.request.urlopen(url) as response:
            data = response.read().decode('utf-8')
            return json.loads(data)
            
    except HTTPError as e:
        print(f"Ошибка HTTP: {e.code} - {e.reason}")
        sys.exit(1)
    except URLError as e:
        print(f"Ошибка URL: {e.reason}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Ошибка парсинга JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Инструмент визуализации графа зависимостей пакетов (Этап 2)"
    )

    # Добавляем параметры командной строки
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
        required=True,
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

    # Парсим аргументы
    args = parser.parse_args()

    # Выводим параметры в формате ключ-значение
    print("Настроенные параметры:")
    print(f"  Пакет: {args.package}")
    print(f"  Репозиторий: {args.repo}")
    print(f"  Тестовый режим: {args.test_mode}")
    print(f"  Версия: {args.version}")
    print(f"  Выходной файл: {args.output}")
    print(f"  ASCII-дерево: {args.ascii_tree}")
    print(f"  Максимальная глубина: {args.max_depth}")
    print()

    # Этап 2: Получение данных о зависимостях
    if args.test_mode == "false":
        print("=== ЭТАП 2: СБОР ДАННЫХ ===")
        
        # Получаем информацию о пакете
        package_info = get_package_info(args.package, args.repo, args.version)
        
        # Извлекаем зависимости
        dependencies = package_info.get('dependencies', {})
        
        if dependencies:
            print(f"Прямые зависимости пакета {args.package}@{args.version}:")
            for dep_name, dep_version in dependencies.items():
                print(f"  - {dep_name}: {dep_version}")
        else:
            print(f"Пакет {args.package}@{args.version} не имеет зависимостей")
    else:
        print("Режим тестирования: пропуск сбора данных из реального репозитория")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)