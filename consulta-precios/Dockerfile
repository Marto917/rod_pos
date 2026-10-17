FROM node:22-alpine

WORKDIR /app
ENV NODE_ENV=production
ENV DATA_DIR=/app/data

COPY package.json ./
COPY server.js ./
COPY lib ./lib
COPY public ./public
COPY catalogo ./catalogo

# El volume de Railway reemplaza /app/data. El proceso corre como root
# para poder escribir la base ahí sin pelear permisos del volume.
RUN mkdir -p /app/data

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=8s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
