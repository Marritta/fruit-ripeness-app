import { useEffect, useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8004";
const MAX_FILE_SIZE = 10 * 1024 * 1024;

const ALLOWED_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
];

function getRipenessClass(ripeness = "") {
  if (ripeness.includes("Перестиг")) {
    return "status-badge status-overripe";
  }

  if (ripeness.includes("Недостиг")) {
    return "status-badge status-unripe";
  }

  return "status-badge status-ripe";
}

function getFruitIcon(fruit = "") {
  const icons = {
    Банан: "🍌",
    Манго: "🥭",
    Полуниця: "🍓",
  };

  return icons[fruit] || "🍈";
}

function formatDate(value) {
  if (!value) return "";

  const date = new Date(
    value.replace(" ", "T")
  );

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("uk-UA", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function App() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);

  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState(null);

  const [loading, setLoading] = useState(false);

  const [
    clearingHistory,
    setClearingHistory,
  ] = useState(false);

  const [pageError, setPageError] = useState("");

  const loadHistory = async () => {
    const response = await fetch(
      `${API_URL}/history`
    );

    if (!response.ok) {
      throw new Error(
        "Не вдалося завантажити історію."
      );
    }

    const data = await response.json();

    setHistory(data);
  };

  const loadStats = async () => {
    const response = await fetch(
      `${API_URL}/stats`
    );

    if (!response.ok) {
      throw new Error(
        "Не вдалося завантажити статистику."
      );
    }

    const data = await response.json();

    setStats(data);
  };

  const refreshData = async () => {
    try {
      setPageError("");

      await Promise.all([
        loadHistory(),
        loadStats(),
      ]);
    } catch (error) {
      setPageError(error.message);
    }
  };

  useEffect(() => {
    refreshData();
  }, []);

  const clearSelectedFile = () => {
    if (preview) {
      URL.revokeObjectURL(preview);
    }

    setFile(null);
    setPreview(null);
    setResult(null);
  };

  const handleFileChange = (event) => {
    const selectedFile =
      event.target.files?.[0];

    if (!selectedFile) return;

    if (
      !ALLOWED_IMAGE_TYPES.includes(
        selectedFile.type
      )
    ) {
      clearSelectedFile();
      event.target.value = "";

      alert(
        "Підтримуються лише зображення " +
          "JPG, JPEG, PNG та WEBP."
      );

      return;
    }

    if (selectedFile.size > MAX_FILE_SIZE) {
      clearSelectedFile();
      event.target.value = "";

      alert(
        "Розмір зображення не повинен " +
          "перевищувати 10 МБ."
      );

      return;
    }

    if (preview) {
      URL.revokeObjectURL(preview);
    }

    setFile(selectedFile);

    setPreview(
      URL.createObjectURL(selectedFile)
    );

    setResult(null);
  };

  const handleAnalyze = async () => {
    if (!file) {
      alert(
        "Спочатку завантажте фото фрукта."
      );

      return;
    }

    const formData = new FormData();

    formData.append("file", file);

    setLoading(true);
    setPageError("");

    try {
      const response = await fetch(
        `${API_URL}/predict-fruit`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail ||
            data.error ||
            "Не вдалося виконати аналіз."
        );
      }

      setResult(data);

      if (data.recognized !== false) {
        await refreshData();
      }
    } catch (error) {
      setResult({
        error: error.message,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleClearHistory = async () => {
    const confirmed = window.confirm(
      "Очистити всю історію аналізів " +
        "і видалити збережені фотографії?"
    );

    if (!confirmed) return;

    setClearingHistory(true);

    try {
      const response = await fetch(
        `${API_URL}/history`,
        {
          method: "DELETE",
        }
      );

      if (!response.ok) {
        throw new Error(
          "Не вдалося очистити історію."
        );
      }

      setHistory([]);

      await loadStats();
    } catch (error) {
      setPageError(error.message);
    } finally {
      setClearingHistory(false);
    }
  };

  const topProbabilities =
    result?.probabilities
      ? Object.entries(result.probabilities)
          .sort(
            (
              [, probabilityA],
              [, probabilityB]
            ) => {
              return (
                probabilityB - probabilityA
              );
            }
          )
          .slice(0, 3)
      : [];

  const mostCommonFruit =
    stats?.fruit_counts?.[0];

  return (
    <main className="app-page">
      <header className="app-header">
        <div>
          <span className="header-label">
            Система комп’ютерного зору
          </span>

          <h1>
            Визначення стиглості фруктів
          </h1>

          <p>
            Завантажте фото банана, манго або
            полуниці. Модель визначить фрукт,
            ступінь його стиглості та сформує
            рекомендацію.
          </p>

          <p className="system-limit">
            Система призначена для аналізу одного
            банана, манго або полуниці на
            зображенні. Для інших об’єктів
            результат може бути невизначеним.
          </p>
        </div>
      </header>

      {pageError && (
        <div className="page-error">
          {pageError}
        </div>
      )}

      <div className="dashboard">
        <section className="panel analysis-panel">
          <div className="section-heading">
            <div>
              <span className="section-number">
                01
              </span>

              <h2>Нове зображення</h2>
            </div>
          </div>

          <label
            className="upload-area"
            htmlFor="fruit-image"
          >
            <input
              id="fruit-image"
              type="file"
              accept=".jpg,.jpeg,.png,.webp"
              onChange={handleFileChange}
            />

            <span className="upload-icon">
              ＋
            </span>

            <strong>
              {file
                ? file.name
                : "Натисніть, щоб обрати зображення"}
            </strong>

            <span>
              Підтримуються JPG, JPEG, PNG та
              WEBP, до 10 МБ
            </span>
          </label>

          {preview && (
            <div className="preview-container">
              <img
                src={preview}
                alt="Завантажений фрукт"
              />
            </div>
          )}

          <button
            className="primary-button"
            onClick={handleAnalyze}
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner"></span>
                Модель аналізує зображення
              </>
            ) : (
              "Визначити стиглість"
            )}
          </button>

          {result && (
            <div
              className="analysis-result"
              aria-live="polite"
            >
              {result.error ? (
                <p className="result-error">
                  {result.error}
                </p>
              ) : result.recognized === false ? (
                <div className="unrecognized-result">
                  <span className="unrecognized-icon">
                    ⚠️
                  </span>

                  <div>
                    <strong>
                      Зображення не розпізнано
                    </strong>

                    <p>{result.warning}</p>

                    <p>
                      Максимальна впевненість
                      моделі:{" "}
                      <strong>
                        {Math.round(
                          result.confidence * 100
                        )}
                        %
                      </strong>
                    </p>
                  </div>
                </div>
              ) : (
                <>
                  <div className="result-header">
                    <div className="result-fruit-icon">
                      {getFruitIcon(result.fruit)}
                    </div>

                    <div>
                      <span className="result-caption">
                        Результат аналізу
                      </span>

                      <h2>{result.fruit}</h2>

                      <span
                        className={getRipenessClass(
                          result.ripeness
                        )}
                      >
                        {result.ripeness}
                      </span>
                    </div>
                  </div>

                  <div className="result-summary">
                    <div>
                      <span>
                        Впевненість моделі
                      </span>

                      <strong>
                        {Math.round(
                          result.confidence * 100
                        )}
                        %
                      </strong>
                    </div>

                    <div>
                      <span>Номер аналізу</span>

                      <strong>
                        #{result.id}
                      </strong>
                    </div>
                  </div>

                  <div className="recommendation-box">
                    <span>Рекомендація</span>

                    <p>
                      {result.recommendation}
                    </p>
                  </div>

                  {topProbabilities.length > 0 && (
                    <div className="probabilities">
                      <h3>
                        Найімовірніші варіанти
                      </h3>

                      {topProbabilities.map(
                        ([label, probability]) => {
                          const percent =
                            Math.round(
                              probability * 100
                            );

                          return (
                            <div
                              className="probability-row"
                              key={label}
                            >
                              <div className="probability-label">
                                <span>{label}</span>

                                <strong>
                                  {percent}%
                                </strong>
                              </div>

                              <div className="progress-track">
                                <div
                                  className="progress-value"
                                  style={{
                                    width: `${percent}%`,
                                  }}
                                ></div>
                              </div>
                            </div>
                          );
                        }
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </section>

        <aside className="side-column">
          <section className="panel">
            <div className="section-heading">
              <div>
                <span className="section-number">
                  02
                </span>

                <h2>Статистика</h2>
              </div>
            </div>

            {stats ? (
              <>
                <div className="stats-cards">
                  <div className="stat-card">
                    <span>
                      Усього аналізів
                    </span>

                    <strong>
                      {stats.total_predictions}
                    </strong>
                  </div>

                  <div className="stat-card">
                    <span>
                      Середня впевненість
                    </span>

                    <strong>
                      {Math.round(
                        stats.average_confidence
                          * 100
                      )}
                      %
                    </strong>
                  </div>

                  <div className="stat-card stat-card-wide">
                    <span>
                      Найчастіший фрукт
                    </span>

                    <strong>
                      {mostCommonFruit
                        ? `${getFruitIcon(
                            mostCommonFruit.fruit
                          )} ${
                            mostCommonFruit.fruit
                          }`
                        : "Немає даних"}
                    </strong>
                  </div>
                </div>

                <div className="stats-group">
                  <h3>
                    Розподіл за фруктами
                  </h3>

                  {(stats.fruit_counts || []).map(
                    (item) => (
                      <div
                        className="stat-row"
                        key={item.fruit}
                      >
                        <span>
                          {getFruitIcon(
                            item.fruit
                          )}{" "}
                          {item.fruit}
                        </span>

                        <strong>
                          {item.count}
                        </strong>
                      </div>
                    )
                  )}
                </div>

                <div className="stats-group">
                  <h3>
                    Розподіл за стиглістю
                  </h3>

                  {(
                    stats.ripeness_counts || []
                  ).map((item) => (
                    <div
                      className="stat-row"
                      key={item.ripeness}
                    >
                      <span
                        className={getRipenessClass(
                          item.ripeness
                        )}
                      >
                        {item.ripeness}
                      </span>

                      <strong>
                        {item.count}
                      </strong>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="empty-message">
                Статистика завантажується…
              </p>
            )}
          </section>

          <section className="panel history-panel">
            <div className="history-heading">
              <div className="section-heading">
                <div>
                  <span className="section-number">
                    03
                  </span>

                  <h2>Історія аналізів</h2>
                </div>
              </div>

              {history.length > 0 && (
                <button
                  className="clear-button"
                  onClick={handleClearHistory}
                  disabled={clearingHistory}
                >
                  {clearingHistory
                    ? "Очищення…"
                    : "Очистити"}
                </button>
              )}
            </div>

            {history.length === 0 ? (
              <div className="empty-history">
                <span>🖼️</span>

                <strong>
                  Історія поки порожня
                </strong>

                <p>
                  Після першого аналізу результат
                  з’явиться тут.
                </p>
              </div>
            ) : (
              <div className="history-list">
                {history.map((item) => (
                  <article
                    className="history-item"
                    key={item.id}
                  >
                    <div className="history-thumbnail">
                      <img
                        src={item.image_url}
                        alt={
                          `${item.fruit} — ` +
                          `${item.ripeness}`
                        }
                        loading="lazy"
                        onError={(event) => {
                          event.currentTarget.style.display =
                            "none";

                          event.currentTarget
                            .parentElement
                            .classList.add(
                              "broken"
                            );
                        }}
                      />
                    </div>

                    <div className="history-content">
                      <div className="history-title">
                        <strong>
                          {getFruitIcon(
                            item.fruit
                          )}{" "}
                          {item.fruit}
                        </strong>

                        <span
                          className={getRipenessClass(
                            item.ripeness
                          )}
                        >
                          {item.ripeness}
                        </span>
                      </div>

                      <div className="history-meta">
                        <span>
                          {Math.round(
                            item.confidence * 100
                          )}
                          % впевненості
                        </span>

                        <span>
                          Аналіз #{item.id}
                        </span>
                      </div>

                      <time>
                        {formatDate(
                          item.created_at
                        )}
                      </time>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </aside>
      </div>
    </main>
  );
}

export default App;

