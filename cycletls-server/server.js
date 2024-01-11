const express = require('express');
const initCycleTLS = require('cycletls');
const app = express();
const port = 3000;

app.use(express.json()); // Middleware for parsing JSON bodies

app.post('/fetch', async (req, res) => {
  const { url, args } = req.body;

  try {
    console.log('Received request for URL:', url); // Log the requested URL

    const cycleTLS = await initCycleTLS();
    const response = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        console.log('Request timed out for URL:', url); // Log timeout
        cycleTLS.exit();
        reject(new Error('Request timed out'));
      }, 10000); // Timeout set to 10000 milliseconds (10 seconds)

      cycleTLS(url, args, 'get')
        .then(response => {
          clearTimeout(timeout);
          resolve(response);
        })
        .catch(reject);
    });

    cycleTLS.exit();
    res.send(response);
  } catch (error) {
    console.error('Error occurred:', error.message); // Log errors
    res.status(500).send({ error: error.message });
  }
});

app.listen(port, () => {
  console.log(`Server listening at http://localhost:${port}`); // Log server start
});
