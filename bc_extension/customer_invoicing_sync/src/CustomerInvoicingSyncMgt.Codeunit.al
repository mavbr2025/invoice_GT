codeunit 71001 "MTM Customer Invoicing Mgt"
{
    procedure LoadCustomFieldValues(Customer: Record Customer; var CfdiCustomerName: Text[250]; var CorreoFactura: Text[250]; var CopySellToAddressTo: Text[50]; var TaxIdentificationType: Text[50]; var CashFlowPaymentTermsCode: Code[20])
    var
        CustomerRef: RecordRef;
    begin
        Clear(CfdiCustomerName);
        Clear(CorreoFactura);
        Clear(CopySellToAddressTo);
        Clear(TaxIdentificationType);
        Clear(CashFlowPaymentTermsCode);

        CustomerRef.GetTable(Customer);

        CfdiCustomerName := ReadTextField(CustomerRef, GetCfdiCustomerNameFieldNo());
        CorreoFactura := ReadTextField(CustomerRef, GetCorreoFacturaFieldNo());
        CopySellToAddressTo := ReadTextField(CustomerRef, GetCopySellToAddressToFieldNo());
        TaxIdentificationType := ReadTextField(CustomerRef, GetTaxIdentificationTypeFieldNo());
        CashFlowPaymentTermsCode := CopyStr(ReadTextField(CustomerRef, GetCashFlowPaymentTermsCodeFieldNo()), 1, MaxStrLen(CashFlowPaymentTermsCode));
    end;

    procedure ApplyCustomFieldValues(var Customer: Record Customer; CfdiCustomerName: Text[250]; CorreoFactura: Text[250]; CopySellToAddressTo: Text[50]; TaxIdentificationType: Text[50]; CashFlowPaymentTermsCode: Code[20])
    var
        CustomerRef: RecordRef;
    begin
        CustomerRef.GetTable(Customer);

        WriteTextField(CustomerRef, GetCfdiCustomerNameFieldNo(), CfdiCustomerName);
        WriteTextField(CustomerRef, GetCorreoFacturaFieldNo(), CorreoFactura);
        WriteTextField(CustomerRef, GetCopySellToAddressToFieldNo(), CopySellToAddressTo);
        WriteTextField(CustomerRef, GetTaxIdentificationTypeFieldNo(), TaxIdentificationType);
        WriteTextField(CustomerRef, GetCashFlowPaymentTermsCodeFieldNo(), CashFlowPaymentTermsCode);

        CustomerRef.SetTable(Customer);
    end;

    local procedure ReadTextField(var CustomerRef: RecordRef; FieldNo: Integer): Text
    var
        FieldRef: FieldRef;
    begin
        if FieldNo <= 0 then
            exit('');

        if not TryGetFieldRef(CustomerRef, FieldNo, FieldRef) then
            exit('');
        exit(Format(FieldRef.Value));
    end;

    local procedure WriteTextField(var CustomerRef: RecordRef; FieldNo: Integer; Value: Text)
    var
        FieldRef: FieldRef;
    begin
        if FieldNo <= 0 then
            exit;

        if not TryGetFieldRef(CustomerRef, FieldNo, FieldRef) then
            exit;
        FieldRef.Value := Value;
    end;

    [TryFunction]
    local procedure TryGetFieldRef(var CustomerRef: RecordRef; FieldNo: Integer; var FieldRef: FieldRef)
    begin
        FieldRef := CustomerRef.Field(FieldNo);
    end;

    local procedure GetCfdiCustomerNameFieldNo(): Integer
    begin
        exit(27007);
    end;

    local procedure GetCorreoFacturaFieldNo(): Integer
    begin
        exit(50110);
    end;

    local procedure GetCopySellToAddressToFieldNo(): Integer
    begin
        exit(7601);
    end;

    local procedure GetTaxIdentificationTypeFieldNo(): Integer
    begin
        exit(14020);
    end;

    local procedure GetCashFlowPaymentTermsCodeFieldNo(): Integer
    begin
        exit(840);
    end;
}
