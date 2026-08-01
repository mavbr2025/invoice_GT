codeunit 71013 "MTM Invoice Customer Email Mgt"
{
    var
        ExpectedSenderLbl: Label 'consuelo@mtmlogix.com', Locked = true;
        LayoutNameLbl: Label 'MTMGTInvoiceStandard202606OnePage', Locked = true;

    procedure SendApprovedInvoiceEmail(PostedInvoice: Record "Sales Invoice Header")
    var
        Audit: Record "MTM Invoice Email Audit";
        Customer: Record Customer;
        CustomerInvoicingMgt: Codeunit "MTM Customer Invoicing Mgt";
        AttachmentBlob: Codeunit "Temp Blob";
        EmailBodyBlob: Codeunit "Temp Blob";
        EmailBodyOutStream: OutStream;
        InvoiceRef: RecordRef;
        Recipient: Text[250];
        CfdiCustomerName: Text[250];
        CorreoFactura: Text[250];
        CopySellToAddressTo: Text[50];
        TaxIdentificationType: Text[50];
        CashFlowPaymentTermsCode: Code[20];
        AttachmentName: Text[250];
        EmailSubject: Text[250];
    begin
        EnsureStamped(PostedInvoice);
        GetOrCreateAudit(Audit, PostedInvoice);
        if Audit.Status = Audit.Status::Sent then
            exit;

        Audit."Attempt Count" += 1;
        Audit.Status := Audit.Status::Pending;
        Audit."Error Text" := '';
        Audit."Sender Email" := ExpectedSenderLbl;
        Audit."Report Layout Name" := LayoutNameLbl;
        Audit.Modify(true);

        if not Customer.Get(PostedInvoice."Sell-to Customer No.") then
            FailAudit(Audit, StrSubstNo('Customer %1 was not found.', PostedInvoice."Sell-to Customer No."));

        CustomerInvoicingMgt.LoadCustomFieldValues(
            Customer,
            CfdiCustomerName,
            CorreoFactura,
            CopySellToAddressTo,
            TaxIdentificationType,
            CashFlowPaymentTermsCode);
        Recipient := CopyStr(CorreoFactura, 1, MaxStrLen(Recipient));
        if Recipient = '' then
            Recipient := Customer."E-Mail";
        ValidateRecipient(Recipient, PostedInvoice."No.");

        Audit.Recipient := Recipient;
        Audit.Modify(true);

        if not TryRenderApprovedInvoicePdf(PostedInvoice, AttachmentBlob) then
            FailAudit(Audit, CopyStr(GetLastErrorText(), 1, MaxStrLen(Audit."Error Text")));

        AttachmentName := CopyStr(StrSubstNo('Factura_%1.pdf', PostedInvoice."No."), 1, MaxStrLen(AttachmentName));
        EmailSubject := CopyStr(StrSubstNo('MTM Logix | Factura electronica %1', PostedInvoice."No."), 1, MaxStrLen(EmailSubject));
        EmailBodyBlob.CreateOutStream(EmailBodyOutStream);
        EmailBodyOutStream.WriteText(BuildCommandEraEmailBody(PostedInvoice, Customer));

        InvoiceRef.GetTable(PostedInvoice);
        if not TrySubmitInvoiceEmail(
            AttachmentBlob,
            AttachmentName,
            EmailBodyBlob,
            EmailSubject,
            Recipient,
            InvoiceRef)
        then
            FailAudit(Audit, CopyStr(GetLastErrorText(), 1, MaxStrLen(Audit."Error Text")));

        Audit.Status := Audit.Status::Sent;
        Audit."Sent At" := CurrentDateTime();
        Audit."Error Text" := '';
        Audit.Modify(true);
    end;

    local procedure EnsureStamped(PostedInvoice: Record "Sales Invoice Header")
    var
        InvoiceRef: RecordRef;
        ElectronicStatus: Text;
    begin
        InvoiceRef.GetTable(PostedInvoice);
        ElectronicStatus := ReadTextField(InvoiceRef, 'Electronic Document Status');
        if UpperCase(ElectronicStatus) <> 'STAMP RECEIVED' then
            Error('Invoice %1 cannot be emailed until FEL status is Stamp Received.', PostedInvoice."No.");
    end;

    local procedure GetOrCreateAudit(var Audit: Record "MTM Invoice Email Audit"; PostedInvoice: Record "Sales Invoice Header")
    begin
        if Audit.Get(PostedInvoice.SystemId) then
            exit;

        Audit.Init();
        Audit."Posted Invoice System Id" := PostedInvoice.SystemId;
        Audit."Posted Invoice No." := PostedInvoice."No.";
        Audit."Customer No." := PostedInvoice."Sell-to Customer No.";
        Audit.Status := Audit.Status::Pending;
        Audit.Insert(true);
    end;

    local procedure ValidateRecipient(Recipient: Text; InvoiceNo: Code[20])
    begin
        if (Recipient = '') or (StrPos(Recipient, '@') = 0) then
            Error('Invoice %1 has no valid invoice recipient. Update Correo Factura or E-Mail on the BC customer.', InvoiceNo);
    end;

    local procedure FailAudit(var Audit: Record "MTM Invoice Email Audit"; ErrorText: Text)
    begin
        Audit.Status := Audit.Status::Failed;
        Audit."Error Text" := CopyStr(ErrorText, 1, MaxStrLen(Audit."Error Text"));
        Audit.Modify(true);
        Error(ErrorText);
    end;

    [TryFunction]
    local procedure TryRenderApprovedInvoicePdf(PostedInvoice: Record "Sales Invoice Header"; var AttachmentBlob: Codeunit "Temp Blob")
    var
        AttachmentOutStream: OutStream;
        InvoiceRef: RecordRef;
    begin
        InvoiceRef.GetTable(PostedInvoice);
        AttachmentBlob.CreateOutStream(AttachmentOutStream);
        Report.SaveAs(Report::FacturaGTM, '', ReportFormat::Pdf, AttachmentOutStream, InvoiceRef);
    end;

    [TryFunction]
    local procedure TrySubmitInvoiceEmail(
        var AttachmentBlob: Codeunit "Temp Blob";
        AttachmentName: Text;
        var EmailBodyBlob: Codeunit "Temp Blob";
        EmailSubject: Text;
        Recipient: Text;
        var InvoiceRef: RecordRef)
    var
        AttachmentInStream: InStream;
        DocumentMailing: Codeunit "Document-Mailing";
    begin
        AttachmentBlob.CreateInStream(AttachmentInStream);
        if not DocumentMailing.EmailFile(
            AttachmentInStream,
            AttachmentName,
            EmailBodyBlob,
            EmailSubject,
            Recipient,
            true,
            Enum::"Email Scenario"::"MTM Invoice Customer Delivery",
            InvoiceRef)
        then
            Error('Business Central could not submit the invoice for email delivery.');
    end;

    local procedure BuildCommandEraEmailBody(PostedInvoice: Record "Sales Invoice Header"; Customer: Record Customer): Text
    begin
        exit(
            '<!doctype html><html><body style="margin:0;background:#F7F5EF;font-family:Noto Sans,Aptos,Arial,sans-serif;color:#050B2E;">' +
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px;">' +
            '<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;background:#FFFFFF;border:1px solid #D9D5CA;">' +
            '<tr><td style="background:#050B2E;padding:26px 32px;border-bottom:5px solid #C9A24A;">' +
            '<div style="color:#C9A24A;font-size:12px;font-weight:700;letter-spacing:1px;">MTM LOGIX</div>' +
            '<div style="color:#FFFFFF;font-size:24px;font-weight:700;margin-top:8px;">FACTURA ELECTRONICA</div></td></tr>' +
            '<tr><td style="padding:32px;font-size:15px;line-height:1.55;">' +
            '<p style="margin:0 0 16px;">Estimado/a ' + EscapeHtml(Customer.Name) + ',</p>' +
            '<p style="margin:0 0 16px;">Adjuntamos la factura electronica <strong>' + EscapeHtml(PostedInvoice."No.") +
            '</strong>. El PDF adjunto contiene el detalle y las referencias operativas del embarque.</p>' +
            '<p style="margin:24px 0 0;">Atentamente,<br><strong>Consuelo Velasquez</strong><br>MTM Logix<br>' + ExpectedSenderLbl + '</p>' +
            '</td></tr><tr><td style="padding:18px 32px;background:#F7F5EF;border-top:1px solid #D9D5CA;color:#5E6474;font-size:12px;">' +
            'MTM Logix | Logistics with command and clarity</td></tr></table></td></tr></table></body></html>');
    end;

    local procedure EscapeHtml(Value: Text): Text
    begin
        Value := Value.Replace('&', '&amp;');
        Value := Value.Replace('<', '&lt;');
        Value := Value.Replace('>', '&gt;');
        Value := Value.Replace('"', '&quot;');
        exit(Value);
    end;

    local procedure ReadTextField(var SourceRef: RecordRef; FieldName: Text): Text
    var
        FieldRef: FieldRef;
        FieldIndex: Integer;
    begin
        for FieldIndex := 1 to SourceRef.FieldCount() do begin
            FieldRef := SourceRef.FieldIndex(FieldIndex);
            if FieldRef.Name() = FieldName then
                exit(Format(FieldRef.Value()));
        end;
        exit('');
    end;
}
