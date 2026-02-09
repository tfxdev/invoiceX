document.addEventListener('DOMContentLoaded', function() {
    const tableBody = document.querySelector('#invoice-items-table tbody');
    const addRowBtn = document.getElementById('add-row-btn');
    const discountInput = document.getElementById('discount-percent');
    const paidInput = document.getElementById('paid-amount');
    const saveInvoiceBtn = document.getElementById('save-invoice-btn');
    const customerSelect = document.getElementById('customer-select');
    const authSignatureInput = document.getElementById('auth-signature');
    const rowTemplate = document.getElementById('invoice-row-template');

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
        subtotalCell.textContent = `BDT ${subtotal.toFixed(2)}`;

        updateTotals();
    }

    function updateTotals() {
        let totalValue = 0;
        tableBody.querySelectorAll('tr').forEach(row => {
            const subtotalText = row.querySelector('.subtotal').textContent;
            totalValue += parseFloat(subtotalText.replace('BDT ', '')) || 0;
        });

        const discountPercent = parseFloat(discountInput.value) || 0;
        const discountAmount = totalValue * (discountPercent / 100);
        const payableValue = totalValue - discountAmount;
        const paidAmount = parseFloat(paidInput.value) || 0;
        const dueAmount = payableValue - paidAmount;

        document.getElementById('total-value').textContent = `BDT ${totalValue.toFixed(2)}`;
        document.getElementById('payable-value').textContent = `BDT ${payableValue.toFixed(2)}`;
        document.getElementById('due-amount').textContent = `BDT ${dueAmount.toFixed(2)}`;
    }

    function addRow() {
        const newRow = rowTemplate.content.cloneNode(true);
        tableBody.appendChild(newRow);
        const addedRow = tableBody.lastElementChild;
        attachRowListeners(addedRow);
        calculateRow(addedRow);
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
            const subtotal = parseFloat(subtotalCell.textContent.replace('BDT ', ''));

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
            total_value: parseFloat(document.getElementById('total-value').textContent.replace('BDT ', '')),
            discount_percent: parseFloat(discountInput.value),
            payable_value: parseFloat(document.getElementById('payable-value').textContent.replace('BDT ', '')),
            paid_amount: parseFloat(paidInput.value),
            due_amount: parseFloat(document.getElementById('due-amount').textContent.replace('BDT ', '')),
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
                window.location.href = `/invoice/${data.invoice_id}/`;
            } else {
                alert(`Error: ${data.message}`);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An unexpected error occurred.');
        });
    });
});
