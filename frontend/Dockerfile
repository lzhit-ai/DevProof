FROM node:22-alpine

# 使用 npmmirror 国内镜像源
RUN npm config set registry https://registry.npmmirror.com

WORKDIR /app
COPY package.json ./
COPY .npmrc ./
RUN npm install
COPY . ./

EXPOSE 5173
CMD ["npm", "run", "dev"]
