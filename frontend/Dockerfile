FROM node:20-alpine

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the frontend code
COPY . .

# Expose port
EXPOSE 5173

# Run the dev server and expose to host
CMD ["npm", "run", "dev", "--", "--host"]
