# Практическая работа 2

## Этап 1: Минимальный прототип с конфигурацией

### Цель
Создать CLI-приложение с настройкой параметров через командную строку.

### Выполненные задачи
- Реализован парсинг аргументов командной строки
- Добавлена валидация обязательных параметров
- Реализован вывод параметров в формате "ключ-значение"
- Добавлена обработка ошибок для всех параметров

### Использование
```bash
cd stage1
python stage1.py --package <name> --repo <url> --test-mode <true/false> [options]
```
### Пример
```bash
python stage1.py --package react --repo https://registry.npmjs.org --test-mode false --version 18.2.0 --output deps.png --ascii-tree true --max-depth 5
```

## Этап 2: Сбор данных
### Цель
Реализовать сбор информации о зависимостях пакетов из npm registry.

### Выполненные задачи
- Реализовано получение данных через NPM Registry API
- Добавлено извлечение прямых зависимостей для указанной версии пакета
- Реализована обработка ошибок сети и парсинга JSON
- Запрещено использование менеджеров пакетов и сторонних библиотек

### Использование
```bash
cd stage2
python stage2.py --package <name> --repo <url> --test-mode false --version <version>
```

### Пример
```bash
python stage2.py --package react --repo https://registry.npmjs.org --test-mode false --version 18.2.0
```
