page 71000 "MTM Customer Invoicing API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'customerSync';
    APIVersion = 'v1.0';
    EntityName = 'customerInvoicing';
    EntitySetName = 'customerInvoicing';
    SourceTable = Customer;
    DelayedInsert = false;
    ODataKeyFields = SystemId;
    Extensible = false;
    InsertAllowed = false;
    DeleteAllowed = false;
    ModifyAllowed = true;

    layout
    {
        area(Content)
        {
            repeater(General)
            {
                field(id; Rec.SystemId)
                {
                    Caption = 'Id';
                    Editable = false;
                }
                field(number; Rec."No.")
                {
                    Caption = 'Number';
                    Editable = false;
                }
                field(displayName; Rec.Name)
                {
                    Caption = 'Display Name';
                }
                field(cfdiCustomerName; CfdiCustomerNameTxt)
                {
                    Caption = 'CFDI Customer Name';
                }
                field(vatRegistrationNumber; Rec."VAT Registration No.")
                {
                    Caption = 'VAT Registration Number';
                }
                field(email; Rec."E-Mail")
                {
                    Caption = 'Email';
                }
                field(invoiceEmail; InvoiceEmailTxt)
                {
                    Caption = 'Invoice Email';
                }
                field(correoFactura; CorreoFacturaTxt)
                {
                    Caption = 'Correo Factura';
                }
                field(phoneNumber; Rec."Phone No.")
                {
                    Caption = 'Phone Number';
                }
                field(contactName; Rec.Contact)
                {
                    Caption = 'Contact Name';
                }
                field(contactEmail; Rec."E-Mail")
                {
                    Caption = 'Contact Email';
                }
                field(contactPhone; Rec."Phone No.")
                {
                    Caption = 'Contact Phone';
                }
                field(website; Rec."Home Page")
                {
                    Caption = 'Website';
                }
                field(paymentTermsCode; Rec."Payment Terms Code")
                {
                    Caption = 'Payment Terms Code';
                }
                field(paymentMethodCode; Rec."Payment Method Code")
                {
                    Caption = 'Payment Method Code';
                }
                field(cashFlowPaymentTermsCode; CashFlowPaymentTermsCodeTxt)
                {
                    Caption = 'Cash Flow Payment Terms Code';
                }
                field(copySellToAddressTo; CopySellToAddressToTxt)
                {
                    Caption = 'Copy Sell-to Address To';
                }
                field(taxIdentificationType; TaxIdentificationTypeTxt)
                {
                    Caption = 'Tax Identification Type';
                }
                field(generalBusinessPostingGroupCode; Rec."Gen. Bus. Posting Group")
                {
                    Caption = 'General Business Posting Group Code';
                }
                field(customerPostingGroupCode; Rec."Customer Posting Group")
                {
                    Caption = 'Customer Posting Group Code';
                }
                field(vatBusinessPostingGroupCode; Rec."VAT Bus. Posting Group")
                {
                    Caption = 'VAT Business Posting Group Code';
                }
                field(creditLimitLcy; Rec."Credit Limit (LCY)")
                {
                    Caption = 'Credit Limit (LCY)';
                }
            }
        }
    }

    trigger OnAfterGetRecord()
    begin
        LoadCustomFields();
        InvoiceEmailTxt := CorreoFacturaTxt;
    end;

    trigger OnModifyRecord(): Boolean
    begin
        if InvoiceEmailTxt <> '' then
            CorreoFacturaTxt := InvoiceEmailTxt;

        CustomerInvoicingMgt.ApplyCustomFieldValues(
            Rec,
            CfdiCustomerNameTxt,
            CorreoFacturaTxt,
            CopySellToAddressToTxt,
            TaxIdentificationTypeTxt,
            CashFlowPaymentTermsCodeTxt);

        exit(true);
    end;

    local procedure LoadCustomFields()
    begin
        CustomerInvoicingMgt.LoadCustomFieldValues(
            Rec,
            CfdiCustomerNameTxt,
            CorreoFacturaTxt,
            CopySellToAddressToTxt,
            TaxIdentificationTypeTxt,
            CashFlowPaymentTermsCodeTxt);
    end;

    var
        CustomerInvoicingMgt: Codeunit "MTM Customer Invoicing Mgt";
        CfdiCustomerNameTxt: Text[250];
        CorreoFacturaTxt: Text[250];
        InvoiceEmailTxt: Text[250];
        CopySellToAddressToTxt: Text[50];
        TaxIdentificationTypeTxt: Text[50];
        CashFlowPaymentTermsCodeTxt: Code[20];
}
