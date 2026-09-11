const { MongoClient } = require("mongodb");
const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient, BatchWriteCommand } = require("@aws-sdk/lib-dynamodb");

// ------------------- ENVIRONMENT CONFIGURATION -------------------
const MONGO_URI = process.env.MONGO_URI;
const MONGO_DB_NAME = process.env.MONGO_DB_NAME;
const MONGO_COLLECTION_NAME = process.env.MONGO_COLLECTION_NAME;

const AWS_REGION = process.env.AWS_REGION || "ap-south-1";
const AWS_ACCESS_KEY_ID = process.env.AWS_ACCESS_KEY_ID;
const AWS_SECRET_ACCESS_KEY = process.env.AWS_SECRET_ACCESS_KEY;
const DYNAMODB_TABLE_NAME = process.env.DYNAMODB_TABLE_NAME || "BUY_PROPERTY";
// -----------------------------------------------------------------

// Validation Check
if (!MONGO_URI || !MONGO_DB_NAME || !MONGO_COLLECTION_NAME || !AWS_ACCESS_KEY_ID || !AWS_SECRET_ACCESS_KEY) {
  console.error(" Error: Missing required Environment Variables in Render settings!");
  process.exit(1);
}

// AWS DynamoDB Client Setup
const ddbClient = new DynamoDBClient({
  region: AWS_REGION,
  credentials: {
    accessKeyId: AWS_ACCESS_KEY_ID,
    secretAccessKey: AWS_SECRET_ACCESS_KEY,
  },
});
const docClient = DynamoDBDocumentClient.from(ddbClient);

async function startMigration() {
  const mongoClient = new MongoClient(MONGO_URI);

  try {
    console.log("Connecting to MongoDB...");
    await mongoClient.connect();
    console.log("Connected to MongoDB successfully.");

    const db = mongoClient.db(MONGO_DB_NAME);
    const collection = db.collection(MONGO_COLLECTION_NAME);

    // MongoDB se saara data fetch karein
    const docs = await collection.find({}).toArray();
    console.log(`Found ${docs.length} records in MongoDB collection '${MONGO_COLLECTION_NAME}'.`);

    if (docs.length === 0) {
      console.log("No data found to migrate.");
      return;
    }

    // Data Formatting for DynamoDB
    const formattedItems = docs.map((doc, index) => {
      // String property_id validation
      const propertyId = doc.property_id
        ? String(doc.property_id)
        : (doc._id ? doc._id.toString() : String(index + 1));

      // Mongo internal _id field ko remove kar rahe hain
      const { _id, ...cleanDoc } = doc;

      return {
        property_id: propertyId,
        ...cleanDoc,
      };
    });

    // Batch upload logic (DynamoDB supports max 25 items per batch)
    const BATCH_SIZE = 25;
    let successCount = 0;

    for (let i = 0; i < formattedItems.length; i += BATCH_SIZE) {
      const chunk = formattedItems.slice(i, i + BATCH_SIZE);

      const writeRequests = chunk.map((item) => ({
        PutRequest: { Item: item },
      }));

      const command = new BatchWriteCommand({
        RequestItems: {
          [DYNAMODB_TABLE_NAME]: writeRequests,
        },
      });

      await docClient.send(command);
      successCount += chunk.length;
      console.log(`Batch Progress: ${successCount} / ${formattedItems.length} items uploaded.`);
    }

    console.log(" Migration Completed Successfully!");
  } catch (error) {
    console.error(" Migration Failed with Error:", error);
  } finally {
    await mongoClient.close();
    console.log("MongoDB connection closed.");
  }
}

startMigration();

