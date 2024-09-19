const express = require('express');
const { Configuration, OpenAIApi } = require('openai');
require('dotenv').config();

const app = express();
app.use(express.json());

// Конфигурация OpenAI
const configuration = new Configuration({
  apiKey: process.env.OPENAI_API_KEY,
});
const openai = new OpenAIApi(configuration);

// Пример эндпоинта для обработки запросов
app.post('/ask', async (req, res) => {
  const { question } = req.body;
  try {
    const response = await openai.createCompletion({
      model: 'text-davinci-003',
      prompt: question,
      max_tokens: 100,
    });
    res.json({ answer: response.data.choices[0].text.trim() });
  } catch (error) {
    res.status(500).send(error.message);
  }
});

// Запуск сервера на порту 3000
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});

