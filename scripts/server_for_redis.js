// dual-protocol-server.js
const net = require('net');
const http = require('http');
const { exec, spawn } = require('child_process');

// Start Redis on a different internal port (not exposed)
const REDIS_INTERNAL_PORT = 6379;

// Start Redis server as a separate process
console.log(`Starting Redis server on internal port ${REDIS_INTERNAL_PORT}...`);
const redisProcess = spawn('redis-server', ['--port', REDIS_INTERNAL_PORT.toString()]);

redisProcess.stdout.on('data', (data) => {
  console.log(`Redis: ${data.toString().trim()}`);
});

redisProcess.stderr.on('data', (data) => {
  console.error(`Redis error: ${data.toString().trim()}`);
});

redisProcess.on('close', (code) => {
  console.log(`Redis process exited with code ${code}`);
});

// Create an HTTP server for health checks
const httpServer = http.createServer((req, res) => {
  if (req.url === "/health" || req.url === "/" || req.url === "/qsynthesis/container/redis-084qf-health") {
    // Check Redis health
    exec(`redis-cli -p ${REDIS_INTERNAL_PORT} ping`, (error, stdout) => {
      if (error || stdout.trim() !== "PONG") {
        console.error(`Health check failed: ${error ? error.message : 'No PONG response'}`);
        res.writeHead(500);
        res.end("Redis is not healthy");
        return;
      }
      res.writeHead(200, {"Content-Type": "application/json"});
      res.end(JSON.stringify({status: "ok", redis: "running"}));
    });
  } else {
    res.writeHead(404);
    res.end("Not found");
  }
});

// Create a TCP server that will handle both Redis and HTTP
const server = net.createServer((socket) => {
  // Buffer for initial data
  let buffer = Buffer.alloc(0);
  let identified = false;

  // Handle data from client
  socket.on('data', (data) => {
    if (identified) return; // Protocol already identified

    // Append data to buffer
    buffer = Buffer.concat([buffer, data]);
    
    // Check if this is HTTP traffic
    const isHttp = buffer.toString().match(/^(GET|POST|PUT|DELETE|HEAD|OPTIONS) /i);
    
    if (isHttp) {
      identified = true;
      handleHttp(socket, buffer);
    } else if (buffer.length >= 4) {
      // Redis protocol typically starts with "*" or "+"
      identified = true;
      handleRedis(socket, buffer);
    }
  });

  socket.on('error', (err) => {
    console.error('Socket error:', err.message);
  });
});

// Handle HTTP traffic
function handleHttp(socket, initialData) {
  console.log('Detected HTTP traffic');
  
  // Create a duplex stream
  const duplex = new net.Socket({ handle: socket._handle });
  duplex.unshift(initialData);
  
  // Connect the socket to our HTTP server
  httpServer.emit('connection', duplex);
}

// Handle Redis traffic
function handleRedis(socket, initialData) {
  console.log('Detected Redis protocol traffic');
  
  // Connect to our internal Redis
  const redisClient = net.createConnection({
    host: 'localhost',
    port: REDIS_INTERNAL_PORT
  });
  
  // Forward the initial data
  redisClient.write(initialData);
  
  // Set up piping in both directions
  socket.pipe(redisClient);
  redisClient.pipe(socket);
  
  // Handle errors
  redisClient.on('error', (err) => {
    console.error('Redis client error:', err.message);
    socket.end();
  });
}

// Start the server on port 3000
const PORT = 3000;
server.listen(PORT, () => {
  console.log(`Dual-protocol server listening on port ${PORT}`);
  console.log(`- Handling HTTP health checks at /qsynthesis/container/redis-084qf-health`);
  console.log(`- Proxying Redis traffic to internal Redis on port ${REDIS_INTERNAL_PORT}`);
});

// Handle process termination
process.on('SIGTERM', () => {
  console.log('Received SIGTERM, shutting down...');
  redisProcess.kill();
  server.close();
});

process.on('SIGINT', () => {
  console.log('Received SIGINT, shutting down...');
  redisProcess.kill();
  server.close();
});