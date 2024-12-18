Желательно использовать версию Python 3.11

Перед запуском в папку youtube-voice-app клонировать репозиторий https://github.com/Pain4D/youtube-voice-app

Создать виртуальную среду с использованием requirements.txt

После этого в файл App.py в соответствующие поля ввести свой токен SteosVoice API по ссылке https://voice.steos.io/voice/api/boosting (важно для использования выбрать тариф, например test), и название файла с куки для работы ютюба (их можно скачать через расширение для хрома "Get cookies.txt")

Также в App.py в функции merge_audio поменять пути к папке generated_audio (ввести путь к папке в которой находится проект в кавычках и добавить в конец generated_audio\\; пример: "ДИСК:\папка_проекта\generated_audio\\")


Для запуска необходимо создать два терминала: в одно ввести "uvicorn app:app --reload --host 0.0.0.0 --port 8000" в другом ввести сначала "cd youtube_voice_app" и после этого "serve -s build"

После этого можно открыть приложение в браузере по ссылке http://localhost:3000
