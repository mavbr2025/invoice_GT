codeunit 71013 "MTM Invoice Customer Email Mgt"
{
    var
        ExpectedSenderLbl: Label 'consuelo@mtmlogix.com', Locked = true;
        LayoutNameLbl: Label 'MTMGTInvoiceStandard202606OnePage', Locked = true;
        ScenarioNotConfiguredErr: Label 'The MTM Invoice Customer Delivery email scenario is not assigned to an email account.';
        WrongSenderErr: Label 'The MTM Invoice Customer Delivery email scenario is assigned to %1. It must be assigned to %2.';

    procedure SendApprovedInvoiceEmail(PostedInvoice: Record "Sales Invoice Header")
    var
        Audit: Record "MTM Invoice Email Audit";
        Customer: Record Customer;
        SenderAccount: Record "Email Account" temporary;
        CustomerInvoicingMgt: Codeunit "MTM Customer Invoicing Mgt";
        AttachmentBlob: Codeunit "Temp Blob";
        Recipient: Text[250];
        CfdiCustomerName: Text[250];
        CorreoFactura: Text[250];
        CopySellToAddressTo: Text[50];
        TaxIdentificationType: Text[50];
        CashFlowPaymentTermsCode: Code[20];
        AttachmentName: Text[250];
        EmailSubject: Text[250];
        EmailBody: Text;
        EvidenceError: Text;
        MessageId: Guid;
    begin
        GetOrCreateAudit(Audit, PostedInvoice);
        if Audit.Status = Audit.Status::Sent then
            exit;

        if not IsStamped(PostedInvoice) then
            FailAudit(Audit, StrSubstNo('Invoice %1 cannot be emailed until FEL status is Stamp Received.', PostedInvoice."No."));

        if not IsNullGuid(Audit."BC Email Message Id") then begin
            if ReconcileNativeSentEmail(Audit, PostedInvoice, EvidenceError) then
                exit;
            if EvidenceError <> '' then
                FailAudit(Audit, EvidenceError);
            if Audit."Native Send Accepted" then
                FailAudit(
                    Audit,
                    StrSubstNo(
                        'Business Central accepted email message %1 for invoice %2, but native Sent Email evidence is not available. The invoice will not be emailed again automatically.',
                        Audit."BC Email Message Id",
                        PostedInvoice."No."));
        end;

        if not ResolveRequiredSenderAccount(SenderAccount, EvidenceError) then
            FailAudit(Audit, EvidenceError);

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
        if (Recipient = '') or (StrPos(Recipient, '@') = 0) then
            FailAudit(
                Audit,
                StrSubstNo(
                    'Invoice %1 has no valid invoice recipient. Update Correo Factura or E-Mail on the BC customer.',
                    PostedInvoice."No."));

        if not TryRenderApprovedInvoicePdf(PostedInvoice, AttachmentBlob) then
            FailAudit(Audit, CopyStr(GetLastErrorText(), 1, MaxStrLen(Audit."Error Text")));

        AttachmentName := CopyStr(StrSubstNo('Factura_%1.pdf', PostedInvoice."No."), 1, MaxStrLen(AttachmentName));
        EmailSubject := CopyStr(StrSubstNo('MTM Logix | Factura electronica %1', PostedInvoice."No."), 1, MaxStrLen(EmailSubject));
        EmailBody := BuildCommandEraEmailBody(PostedInvoice, Customer);
        if not TryPrepareInvoiceEmail(
            PostedInvoice,
            AttachmentBlob,
            AttachmentName,
            EmailSubject,
            EmailBody,
            Recipient,
            MessageId)
        then
            FailAudit(Audit, CopyStr(GetLastErrorText(), 1, MaxStrLen(Audit."Error Text")));

        Audit.Get(PostedInvoice.SystemId);
        Audit."Attempt Count" += 1;
        Audit.Status := Audit.Status::Pending;
        Audit.Recipient := Recipient;
        Audit."Sender Email" := CopyStr(SenderAccount."Email Address", 1, MaxStrLen(Audit."Sender Email"));
        Audit."Sender Account Id" := SenderAccount."Account Id";
        Audit."BC Email Message Id" := MessageId;
        Audit."Native Send Accepted" := false;
        Audit."Native Sent Verified" := false;
        Audit."Last Attempt At" := CurrentDateTime();
        Clear(Audit."Sent At");
        Audit."Error Text" := '';
        Audit."Report Layout Name" := LayoutNameLbl;
        Audit.Modify(true);
        Commit();

        if not TrySendInvoiceEmail(MessageId, SenderAccount) then begin
            Audit.Get(PostedInvoice.SystemId);
            Audit."Native Send Accepted" := false;
            FailAudit(Audit, CopyStr(GetLastErrorText(), 1, MaxStrLen(Audit."Error Text")));
        end;

        Audit.Get(PostedInvoice.SystemId);
        Audit."Native Send Accepted" := true;
        Audit.Modify(true);
        Commit();

        if ReconcileNativeSentEmail(Audit, PostedInvoice, EvidenceError) then
            exit;
        if EvidenceError = '' then
            EvidenceError := StrSubstNo(
                'Business Central accepted email message %1 for invoice %2, but its exact native Sent Email record was not found.',
                MessageId,
                PostedInvoice."No.");
        FailAudit(Audit, EvidenceError);
    end;

    local procedure IsStamped(PostedInvoice: Record "Sales Invoice Header"): Boolean
    var
        InvoiceRef: RecordRef;
        ElectronicStatus: Text;
    begin
        InvoiceRef.GetTable(PostedInvoice);
        ElectronicStatus := ReadTextField(InvoiceRef, 'Electronic Document Status');
        exit(UpperCase(ElectronicStatus) = 'STAMP RECEIVED');
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
        Commit();
    end;

    local procedure ResolveRequiredSenderAccount(var SenderAccount: Record "Email Account" temporary; var ErrorText: Text): Boolean
    var
        EmailScenario: Codeunit "Email Scenario";
    begin
        ErrorText := '';
        if not EmailScenario.IsThereEmailAccountSetForScenario(Enum::"Email Scenario"::"MTM Invoice Customer Delivery") then begin
            ErrorText := ScenarioNotConfiguredErr;
            exit(false);
        end;
        if not EmailScenario.GetEmailAccount(Enum::"Email Scenario"::"MTM Invoice Customer Delivery", SenderAccount) then begin
            ErrorText := ScenarioNotConfiguredErr;
            exit(false);
        end;
        if LowerCase(SenderAccount."Email Address") <> LowerCase(ExpectedSenderLbl) then begin
            ErrorText := StrSubstNo(WrongSenderErr, SenderAccount."Email Address", ExpectedSenderLbl);
            exit(false);
        end;
        exit(true);
    end;

    local procedure ReconcileNativeSentEmail(
        var Audit: Record "MTM Invoice Email Audit";
        PostedInvoice: Record "Sales Invoice Header";
        var EvidenceError: Text): Boolean
    var
        SentEmail: Record "Sent Email" temporary;
        Email: Codeunit Email;
    begin
        EvidenceError := '';
        if IsNullGuid(Audit."BC Email Message Id") then
            exit(false);

        Email.GetSentEmailsForRecord(Database::"Sales Invoice Header", PostedInvoice.SystemId, SentEmail);
        if not SentEmail.FindSet() then
            exit(false);

        repeat
            if SentEmail.GetMessageId() = Audit."BC Email Message Id" then begin
                if SentEmail.GetAccountId() <> Audit."Sender Account Id" then begin
                    EvidenceError := StrSubstNo(
                        'Native Sent Email evidence for message %1 used an unexpected Business Central sender account.',
                        Audit."BC Email Message Id");
                    exit(false);
                end;
                Audit.Get(PostedInvoice.SystemId);
                Audit.Status := Audit.Status::Sent;
                Audit."Native Send Accepted" := true;
                Audit."Native Sent Verified" := true;
                Audit."Sent At" := CurrentDateTime();
                Audit."Error Text" := '';
                Audit.Modify(true);
                Commit();
                exit(true);
            end;
        until SentEmail.Next() = 0;

        exit(false);
    end;

    local procedure FailAudit(var Audit: Record "MTM Invoice Email Audit"; ErrorText: Text)
    begin
        Audit.Get(Audit."Posted Invoice System Id");
        Audit.Status := Audit.Status::Failed;
        Audit."Error Text" := CopyStr(ErrorText, 1, MaxStrLen(Audit."Error Text"));
        Audit.Modify(true);
        Commit();
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
    local procedure TryPrepareInvoiceEmail(
        PostedInvoice: Record "Sales Invoice Header";
        var AttachmentBlob: Codeunit "Temp Blob";
        AttachmentName: Text;
        EmailSubject: Text;
        EmailBody: Text;
        Recipient: Text;
        var MessageId: Guid)
    var
        EmailMessage: Codeunit "Email Message";
        Email: Codeunit Email;
        AttachmentInStream: InStream;
    begin
        EmailMessage.Create(Recipient, EmailSubject, EmailBody, true);
        AttachmentBlob.CreateInStream(AttachmentInStream);
        EmailMessage.AddAttachment(AttachmentName, 'application/pdf', AttachmentInStream);
        Email.AddRelation(
            EmailMessage,
            Database::"Sales Invoice Header",
            PostedInvoice.SystemId,
            Enum::"Email Relation Type"::"Primary Source",
            Enum::"Email Relation Origin"::"Compose Context");
        MessageId := EmailMessage.GetId();
    end;

    [TryFunction]
    local procedure TrySendInvoiceEmail(MessageId: Guid; var SenderAccount: Record "Email Account" temporary)
    var
        EmailMessage: Codeunit "Email Message";
        Email: Codeunit Email;
    begin
        if not EmailMessage.Get(MessageId) then
            Error('Business Central email message %1 could not be loaded.', MessageId);
        if not Email.Send(EmailMessage, SenderAccount) then
            Error('Business Central could not send the invoice through the configured email account.');
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
