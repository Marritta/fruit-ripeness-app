from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
import tensorflow as tf
import numpy as np
import io
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


app = FastAPI(
    title="Система визначення стиглості фруктів",
    version="5.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = Path(__file__).resolve().parent

MODEL_PATH = BASE_DIR / "fruit_ripeness_v5_model.keras"
CLASS_NAMES_PATH = BASE_DIR / "fruit_ripeness_v5_class_names.json"
DB_PATH = BASE_DIR / "fruit_ripeness_v5.db"
UPLOADS_DIR = BASE_DIR / "uploads"


MAX_FILE_SIZE = 10 * 1024 * 1024  
MIN_IMAGE_WIDTH = 100
MIN_IMAGE_HEIGHT = 100

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

ALLOWED_IMAGE_FORMATS = {
    "JPEG",
    "PNG",
    "WEBP",
}


MIN_RECOGNITION_CONFIDENCE = 0.60
MIN_CLASS_MARGIN = 0.10


Image.MAX_IMAGE_PIXELS = 25_000_000


UPLOADS_DIR.mkdir(exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory=UPLOADS_DIR),
    name="uploads",
)


def build_image_url(
    request: Request,
    saved_image_path: str,
) -> str:
    filename = Path(saved_image_path).name

    return str(
        request.url_for(
            "uploads",
            path=filename,
        )
    )


model = tf.keras.models.load_model(MODEL_PATH)

with open(
    CLASS_NAMES_PATH,
    "r",
    encoding="utf-8",
) as file:
    class_names = json.load(file)


fruit_labels = {
    "banana": "Банан",
    "mango": "Манго",
    "strawberry": "Полуниця",
}

ripeness_labels = {
    "unripe": "Недостиглий",
    "ripe": "Стиглий",
    "overripe": "Перестиглий",
}


def init_database() -> None:
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT,
            saved_image_path TEXT,
            fruit TEXT,
            ripeness TEXT,
            predicted_class TEXT,
            confidence REAL,
            probabilities TEXT,
            recommendation TEXT,
            model_version TEXT,
            created_at TEXT
        )
    """)

    connection.commit()
    connection.close()


init_database()


def parse_class_name(
    class_name: str,
) -> tuple[str, str]:
    parts = class_name.split("_", 1)

    if len(parts) == 2:
        return parts[0], parts[1]

    return class_name, "unknown"


def get_recommendation(
    fruit: str,
    ripeness: str,
) -> str:
    fruit_ua = fruit_labels.get(fruit, fruit)

    if ripeness == "unripe":
        return (
            f"Фрукт визначено як недостиглий. "
            "Його доцільно залишити достигати "
            "та перевірити пізніше."
        )

    if ripeness == "ripe":
        return (
            f"Фрукт визначено як стиглий. "
            "Перед використанням перевірте відсутність "
            "пошкоджень, плісняви та неприємного запаху."
        )

    if ripeness == "overripe":
        return (
            f"Фрукт визначено як перестиглий. "
            "Перед використанням перевірте його запах, "
            "текстуру, цілісність і відсутність ознак плісняви. "
            "Система оцінює лише зовнішній вигляд."
        )

    return (
        "Не вдалося сформувати рекомендацію. "
        "Перевірте стан фрукта самостійно."
    )


def validate_and_prepare_image(
    contents: bytes,
    content_type: str | None,
) -> np.ndarray:
    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Завантажений файл порожній.",
        )

    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Підтримуються лише зображення "
                "JPG, JPEG, PNG та WEBP."
            ),
        )

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                "Розмір зображення не повинен "
                "перевищувати 10 МБ."
            ),
        )

    try:
        with Image.open(
            io.BytesIO(contents)
        ) as test_image:
            image_format = test_image.format
            test_image.verify()

        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise HTTPException(
                status_code=400,
                detail="Формат зображення не підтримується.",
            )

        with Image.open(
            io.BytesIO(contents)
        ) as image:
            image = ImageOps.exif_transpose(image)

            width, height = image.size

            if (
                width < MIN_IMAGE_WIDTH
                or height < MIN_IMAGE_HEIGHT
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Зображення має занадто малу "
                        "роздільну здатність. "
                        "Мінімальний розмір — "
                        "100 × 100 пікселів."
                    ),
                )

            image = image.convert("RGB")

            image = image.resize(
                (224, 224),
                Image.Resampling.LANCZOS,
            )

            image_array = np.asarray(
                image,
                dtype=np.float32,
            )

    except HTTPException:
        raise

    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
    ) as error:
        raise HTTPException(
            status_code=400,
            detail=(
                "Файл пошкоджений або не є "
                "коректним зображенням."
            ),
        ) from error

    return np.expand_dims(
        image_array,
        axis=0,
    )


def save_uploaded_image(
    original_filename: str,
    contents: bytes,
) -> str:
    file_extension = Path(
        original_filename
    ).suffix.lower()

    if file_extension not in [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    ]:
        file_extension = ".jpg"

    unique_filename = (
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex}"
        f"{file_extension}"
    )

    saved_path = UPLOADS_DIR / unique_filename

    with open(
        saved_path,
        "wb",
    ) as file:
        file.write(contents)

    return f"uploads/{unique_filename}"


def save_prediction_to_database(
    original_filename: str,
    saved_image_path: str,
    fruit: str,
    ripeness: str,
    predicted_class: str,
    confidence: float,
    probabilities: dict,
    recommendation: str,
) -> int:
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO predictions (
            original_filename,
            saved_image_path,
            fruit,
            ripeness,
            predicted_class,
            confidence,
            probabilities,
            recommendation,
            model_version,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        original_filename,
        saved_image_path,
        fruit,
        ripeness,
        predicted_class,
        confidence,
        json.dumps(
            probabilities,
            ensure_ascii=False,
        ),
        recommendation,
        "fruit_ripeness_v5",
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    ))

    prediction_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return int(prediction_id)


@app.get("/")
def home():
    return {
        "message": (
            "Fruit Ripeness V5 API "
            "with database is running"
        ),
        "classes": class_names,
    }


@app.post("/predict-fruit")
async def predict_fruit(
    request: Request,
    file: UploadFile = File(...),
):
    contents = await file.read()

    prepared_image = validate_and_prepare_image(
        contents=contents,
        content_type=file.content_type,
    )

    predictions = model.predict(
        prepared_image,
        verbose=0,
    )[0]

    predicted_index = int(
        np.argmax(predictions)
    )

    predicted_class = class_names[
        predicted_index
    ]

    confidence = float(
        predictions[predicted_index]
    )

    sorted_probabilities = np.sort(
        predictions
    )[::-1]

    class_margin = float(
        sorted_probabilities[0]
        - sorted_probabilities[1]
    )

    probabilities = {}

    for class_name, probability in zip(
        class_names,
        predictions,
    ):
        fruit_name, ripeness_name = (
            parse_class_name(class_name)
        )

        fruit_label = fruit_labels.get(
            fruit_name,
            fruit_name,
        )

        ripeness_label = ripeness_labels.get(
            ripeness_name,
            ripeness_name,
        )

        label = (
            f"{fruit_label} — "
            f"{ripeness_label}"
        )

        probabilities[label] = round(
            float(probability),
            4,
        )

    if (
        confidence < MIN_RECOGNITION_CONFIDENCE
        or class_margin < MIN_CLASS_MARGIN
    ):
        return {
            "recognized": False,
            "confidence": round(
                confidence,
                4,
            ),
            "class_margin": round(
                class_margin,
                4,
            ),
            "warning": (
                "Не вдалося надійно визначити "
                "підтримуваний фрукт. "
                "Завантажте чітке фото одного "
                "банана, манго або полуниці "
                "на простому фоні."
            ),
            "probabilities": probabilities,
        }

    fruit, ripeness = parse_class_name(
        predicted_class
    )

    fruit_ua = fruit_labels.get(
        fruit,
        fruit,
    )

    ripeness_ua = ripeness_labels.get(
        ripeness,
        ripeness,
    )

    recommendation = get_recommendation(
        fruit,
        ripeness,
    )

    saved_image_path = save_uploaded_image(
        file.filename or "image.jpg",
        contents,
    )

    prediction_id = (
        save_prediction_to_database(
            original_filename=(
                file.filename or "image.jpg"
            ),
            saved_image_path=saved_image_path,
            fruit=fruit_ua,
            ripeness=ripeness_ua,
            predicted_class=predicted_class,
            confidence=round(
                confidence,
                4,
            ),
            probabilities=probabilities,
            recommendation=recommendation,
        )
    )

    return {
        "recognized": True,
        "id": prediction_id,
        "fruit": fruit_ua,
        "ripeness": ripeness_ua,
        "class_name": predicted_class,
        "confidence": round(
            confidence,
            4,
        ),
        "recommendation": recommendation,
        "warning": "",
        "probabilities": probabilities,
        "image_url": build_image_url(
            request,
            saved_image_path,
        ),
    }


@app.get("/history")
def get_history(
    request: Request,
):
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            original_filename,
            saved_image_path,
            fruit,
            ripeness,
            predicted_class,
            confidence,
            recommendation,
            model_version,
            created_at
        FROM predictions
        ORDER BY id DESC
        LIMIT 50
    """)

    rows = cursor.fetchall()
    connection.close()

    history = []

    for row in rows:
        item = dict(row)

        item["image_url"] = build_image_url(
            request,
            item["saved_image_path"],
        )

        history.append(item)

    return history


@app.get("/history/{prediction_id}")
def get_prediction_details(
    prediction_id: int,
    request: Request,
):
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM predictions
        WHERE id = ?
    """, (prediction_id,))

    row = cursor.fetchone()
    connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Запис не знайдено.",
        )

    item = dict(row)

    item["probabilities"] = json.loads(
        item["probabilities"]
    )

    item["image_url"] = build_image_url(
        request,
        item["saved_image_path"],
    )

    return item


@app.get("/stats")
def get_stats():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS total_predictions
        FROM predictions
        """
    )

    total_predictions = cursor.fetchone()[
        "total_predictions"
    ]

    cursor.execute("""
        SELECT fruit, COUNT(*) AS count
        FROM predictions
        GROUP BY fruit
        ORDER BY count DESC
    """)

    fruit_counts = [
        dict(row)
        for row in cursor.fetchall()
    ]

    cursor.execute("""
        SELECT ripeness, COUNT(*) AS count
        FROM predictions
        GROUP BY ripeness
        ORDER BY count DESC
    """)

    ripeness_counts = [
        dict(row)
        for row in cursor.fetchall()
    ]

    cursor.execute("""
        SELECT AVG(confidence) AS average_confidence
        FROM predictions
    """)

    average_confidence = cursor.fetchone()[
        "average_confidence"
    ]

    connection.close()

    if average_confidence is None:
        average_confidence = 0

    return {
        "total_predictions": total_predictions,
        "fruit_counts": fruit_counts,
        "ripeness_counts": ripeness_counts,
        "average_confidence": round(
            float(average_confidence),
            4,
        ),
    }


@app.delete("/history")
def clear_history():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT saved_image_path
        FROM predictions
    """)

    rows = cursor.fetchall()

    deleted_images = 0

    for row in rows:
        image_path = (
            BASE_DIR
            / row["saved_image_path"]
        )

        try:
            if image_path.exists():
                image_path.unlink()
                deleted_images += 1

        except OSError:
            pass

    cursor.execute(
        "DELETE FROM predictions"
    )

    try:
        cursor.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name = 'predictions'
            """
        )

    except sqlite3.OperationalError:
        pass

    connection.commit()
    connection.close()

    return {
        "message": (
            "Історію аналізів очищено."
        ),
        "deleted_images": deleted_images,
    }

