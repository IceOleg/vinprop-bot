# Используем последнюю версию Node.js
FROM node:20

# Создаем рабочую директорию
WORKDIR /app

# Копируем package.json и package-lock.json
COPY package*.json ./

# Устанавливаем зависимости
RUN npm install

# Копируем остальные файлы проекта
COPY . .

# Указываем порт для прослушивания
ENV PORT 8080

# Запуск приложения
CMD ["node", "index.js"]

