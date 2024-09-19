// Импортируем необходимые модули
const express = require('express');
const axios = require('axios');
require('dotenv').config();

// Инициализация приложения Express
const app = express();
app.use(express.json());

// Конфигурация бота
const TELEGRAM_API = `https://api.telegram.org/bot${process.env.TELEGRAM_TOKEN}`;
const URI = `/webhook/${process.env.TELEGRAM_TOKEN}`;
const WEBHOOK_URL = `${process.env.WEBHOOK_URL}${URI}`;

// Установка вебхука
app.post(`/setWebhook`, async (req, res) => {
  try {
    const response = await axios.post(`${TELEGRAM_API}/setWebhook`, {
      url: WEBHOOK_URL,
    });
    res.status(200).send(response.data);
  } catch (error) {
    console.error("Error setting webhook:", error);
    res.status(500).send(error.message);
  }
});

// Обработка вебхука
app.post(URI, async (req, res) => {
  console.log('Received message:', req.body);

  const message = req.body.message;
  if (message && message.text) {
    const chatId = message.chat.id;
    const text = message.text;

    // Отправка ответа обратно в Telegram
    try {
      await axios.post(`${TELEGRAM_API}/sendMessage`, {
        chat_id: chatId,
        text: `You said: ${text}`,
      });
    } catch (error) {
      console.error("Error sending message:", error);
    }
  }

  // Отправляем успешный ответ на вебхук
  return res.sendStatus(200);
});

// Запуск сервера
const PORT = process.env.PORT || 8080;
app.listen(PORT, async () => {
  console.log(`Server is running on port ${PORT}`);

  try {
    // Автоматическая установка вебхука при запуске сервера
    const response = await axios.post(`${TELEGRAM_API}/setWebhook`, {
      url: WEBHOOK_URL,
    });
    console.log('Webhook set:', response.data);
  } catch (error) {
    console.error("Error setting webhook during server start:", error);
  }
});

