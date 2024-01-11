const express = require('express');
const initCycleTLS = require('cycletls');
const app = express();
const port = 3000;

app.use(express.json()); // Middleware for parsing JSON bodies

app.post('/fetch', async (req, res) => {
  const { url, args } = req.body;

  try {
    const cycleTLS = await initCycleTLS();
    const response = await cycleTLS(url, args, 'get');
    cycleTLS.exit();
    res.send(response);
  } catch (error) {
    res.status(500).send({ error: error.message });
  }
});

app.listen(port, () => {
  console.log(`Server listening at http://localhost:${port}`);
});
