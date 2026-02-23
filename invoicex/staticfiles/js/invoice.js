document.addEventListener('DOMContentLoaded', function() {
    const tableBody = document.querySelector('#invoice-items-table tbody');
    const addRowBtn = document.getElementById('add-row-btn');
    const discountInput = document.getElementById('discount-percent');
    const paidInput = document.getElementById('paid-amount');
    const saveInvoiceBtn = document.getElementById('save-invoice-btn');
    const customerSelect = document.getElementById('customer-select');
    const authSignatureInput = document.getElementById('auth-signature');
    
    // Store product options HTML to reuse when adding new rows
    const productOptions = document.querySelector('.product-select') ? document.querySelector('.product-select').innerHTML : '';

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function calculateRow(row) {
        const productSelect = row.querySelector('.product-select');
        const quantityInput = row.querySelector('.quantity');
        const priceInput = row.querySelector('.price');
        const subtotalCell = row.querySelector('.subtotal');

        const selectedOption = productSelect.options[productSelect.selectedIndex];
        let price = parseFloat(priceInput.value);
        
        if (isNaN(price) && selectedOption && selectedOption.dataset.price) {
            price = parseFloat(selectedOption.dataset.price);
            priceInput.value = price.toFixed(2);
        } else if (isNaN(price)) {
            price = 0;
        }

        const quantity = parseInt(quantityInput.value) || 0;
        const subtotal = quantity * price;
        subtotalCell.textContent = `$${subtotal.toFixed(2)}`;

        updateTotals();
    }

    function updateTotals() {
        let totalValue = 0;
        tableBody.querySelectorAll('tr').forEach(row => {
            const subtotalText = row.querySelector('.subtotal').textContent;
            totalValue += parseFloat(subtotalText.replace('$', '')) || 0;
        });

        const discountPercent = parseFloat(discountInput.value) || 0;
        const discountAmount = totalValue * (discountPercent / 100);
        const payableValue = totalValue - discountAmount;
        const paidAmount = parseFloat(paidInput.value) || 0;
        const dueAmount = payableValue - paidAmount;

        document.getElementById('total-value').textContent = `$${totalValue.toFixed(2)}`;
        document.getElementById('payable-value').textContent = `$${payableValue.toFixed(2)}`;
        document.getElementById('due-amount').textContent = `$${dueAmount.toFixed(2)}`;
    }

    function addRow() {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td>
                <select class="form-control product-select">
                    ${productOptions}
                </select>
            </td>
            <td><input type="number" class="form-control quantity" value="1" min="1"></td>
            <td><input type="number" class="form-control price" step="0.01"></td>
            <td class="subtotal text-end fw-bold">$0.00</td>
            <td class="text-center"><button class="btn btn-danger btn-sm delete-row-btn"><i class="fas fa-trash-alt"></i></button></td>
        `;
        tableBody.appendChild(newRow);
        attachRowListeners(newRow);
        calculateRow(newRow); // Calculate for the new row immediately
    }

    function deleteRow(e) {
        const btn = e.target.closest('.delete-row-btn');
        if (btn) {
            btn.closest('tr').remove();
            updateTotals();
        }
    }

    function attachRowListeners(row) {
        row.querySelector('.product-select').addEventListener('change', () => calculateRow(row));
        row.querySelector('.quantity').addEventListener('input', () => calculateRow(row));
        row.querySelector('.price').addEventListener('input', () => calculateRow(row));
    }

    // Initial setup
    addRow(); // Start with one empty row
    addRowBtn.addEventListener('click', addRow);
    tableBody.addEventListener('click', deleteRow);
    discountInput.addEventListener('input', updateTotals);
    paidInput.addEventListener('input', updateTotals);

    saveInvoiceBtn.addEventListener('click', function() {
        const invoiceItems = [];
        tableBody.querySelectorAll('tr').forEach(row => {
            const productSelect = row.querySelector('.product-select');
            const quantityInput = row.querySelector('.quantity');
            const subtotalCell = row.querySelector('.subtotal');
            const productId = productSelect.value;
            const quantity = parseInt(quantityInput.value);
            const subtotal = parseFloat(subtotalCell.textContent.replace('$', ''));

            if (productId && quantity > 0) {
                invoiceItems.push({
                    product_id: productId,
                    quantity: quantity,
                    subtotal: subtotal
                });
            }
        });

        if (invoiceItems.length === 0) {
            alert("Please add at least one valid invoice item.");
            return;
        }

        const invoiceData = {
            customer_id: customerSelect.value || null,
            total_value: parseFloat(document.getElementById('total-value').textContent.replace('$', '')),
            discount_percent: parseFloat(discountInput.value),
            payable_value: parseFloat(document.getElementById('payable-value').textContent.replace('$', '')),
            paid_amount: parseFloat(paidInput.value),
            due_amount: parseFloat(document.getElementById('due-amount').textContent.replace('$', '')),
            authorized_signature: authSignatureInput.value,
            items: invoiceItems
        };

        const csrftoken = getCookie('csrftoken');

        fetch('/api/save_invoice/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify(invoiceData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                window.location.href = \`/invoice/\${data.invoice_id}/\`;
            } else {
                alert(`Error: \${data.message}`);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An unexpected error occurred.');
        });
    });
});