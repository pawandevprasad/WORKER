{
  "name": "mongo-to-dynamo-migration",
  "version": "1.0.0",
  "description": "Migrate data from MongoDB to AWS DynamoDB",
  "main": "migrate.js",
  "scripts": {
    "start": "node migrate.js"
  },
  "dependencies": {
    "@aws-sdk/client-dynamodb": "^3.500.0",
    "@aws-sdk/lib-dynamodb": "^3.500.0",
    "mongodb": "^6.3.0"
  }
}

