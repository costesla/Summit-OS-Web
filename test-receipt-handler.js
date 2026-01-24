/**
 * COS Tesla LLC — Receipt Handler Test Script
 * Tests the receipt-combined-handler with sample trip data
 */

import handler from './src/lib/receipt-combined-handler';
import sampleTrip from './sample-trip.json';

async function testReceiptHandler() {
    console.log('🧪 Testing Receipt Handler...\n');
    console.log('📋 Sample Trip Data:');
    console.log(`   Trip ID: ${sampleTrip.TripData.Id}`);
    console.log(`   Passenger: ${sampleTrip.PassengerData.firstName}`);
    console.log(`   Email: ${sampleTrip.PassengerData.email}`);
    console.log(`   Total: $${sampleTrip.FareData.Total}\n`);

    try {
        console.log('🚀 Calling receipt handler...\n');
        const result = await handler(sampleTrip);

        if ('error' in result) {
            console.error('❌ Error:', result.error);
            process.exit(1);
        }

        console.log('✅ Receipt generated successfully!\n');
        console.log('📧 Send Status:', result.send);
        console.log('\n📄 HTML Preview (first 500 chars):');
        console.log(result.html.substring(0, 500) + '...\n');
        console.log('📝 Text Preview (first 500 chars):');
        console.log(result.text.substring(0, 500) + '...\n');

        // Save outputs for inspection
        const fs = require('fs');
        fs.writeFileSync('test-output-receipt.html', result.html);
        fs.writeFileSync('test-output-receipt.txt', result.text);
        console.log('💾 Full outputs saved to:');
        console.log('   - test-output-receipt.html');
        console.log('   - test-output-receipt.txt');

    } catch (error) {
        console.error('❌ Test failed:', error);
        process.exit(1);
    }
}

testReceiptHandler();
