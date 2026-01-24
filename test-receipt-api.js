/**
 * Test the receipt API endpoint
 * Run this after starting the dev server: npm run dev
 * Then run: node test-receipt-api.js
 */

const fs = require('fs');

async function testReceiptAPI() {
    console.log('🧪 Testing Receipt API Endpoint...\n');

    // Load sample trip data
    const sampleTrip = JSON.parse(fs.readFileSync('./sample-trip.json', 'utf-8'));

    console.log('📋 Sample Trip Data:');
    console.log(`   Trip ID: ${sampleTrip.TripData.Id}`);
    console.log(`   Passenger: ${sampleTrip.PassengerData.firstName}`);
    console.log(`   Email: ${sampleTrip.PassengerData.email}`);
    console.log(`   Total: $${sampleTrip.FareData.Total}\n`);

    try {
        console.log('🚀 Calling POST /api/receipt-graph...\n');

        const response = await fetch('http://localhost:3000/api/receipt-graph', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(sampleTrip)
        });

        const result = await response.json();

        if (!response.ok) {
            console.error('❌ API Error:', result.error);
            console.error('Status:', response.status);
            process.exit(1);
        }

        console.log('✅ Receipt sent successfully!\n');
        console.log('📧 Send Status:', result.send);
        console.log('📊 Preview:', result.preview);
        console.log('\n🎉 SUCCESS! Check the inbox for:', sampleTrip.PassengerData.email);

    } catch (error) {
        console.error('❌ Test failed:', error.message);
        console.error('\n💡 Make sure the dev server is running:');
        console.error('   npm run dev');
        process.exit(1);
    }
}

testReceiptAPI();
