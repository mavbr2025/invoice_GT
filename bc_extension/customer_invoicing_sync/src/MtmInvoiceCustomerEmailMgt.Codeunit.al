codeunit 71013 "MTM Invoice Customer Email Mgt"
{
    var
        ExpectedSenderLbl: Label 'consuelo@mtmlogix.com', Locked = true;
        TestRecipientLbl: Label 'mario@mtmlogix.com', Locked = true;
        LayoutNameLbl: Label 'MTMGTInvoiceStandard202606OnePage', Locked = true;
        LogoUrlLbl: Label 'https://mhth6mu5g8.execute-api.us-east-1.amazonaws.com/assets/mtm-logix-email-logo-porcelain-v1.png', Locked = true;
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
            EvidenceError := GetSendFailureEvidence(PostedInvoice, MessageId, GetLastErrorText());
            FailAudit(Audit, CopyStr(EvidenceError, 1, MaxStrLen(Audit."Error Text")));
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

    procedure SendApprovedInvoiceTestEmailToMario(PostedInvoice: Record "Sales Invoice Header")
    var
        Customer: Record Customer;
        SenderAccount: Record "Email Account" temporary;
        AttachmentBlob: Codeunit "Temp Blob";
        AttachmentName: Text[250];
        EmailSubject: Text[250];
        EmailBody: Text;
        EvidenceError: Text;
        MessageId: Guid;
    begin
        if not IsStamped(PostedInvoice) then
            Error('Invoice %1 cannot be used for the email canary until FEL status is Stamp Received.', PostedInvoice."No.");

        if not ResolveRequiredSenderAccount(SenderAccount, EvidenceError) then
            Error(EvidenceError);

        if not Customer.Get(PostedInvoice."Sell-to Customer No.") then
            Error('Customer %1 was not found.', PostedInvoice."Sell-to Customer No.");

        if not TryRenderApprovedInvoicePdf(PostedInvoice, AttachmentBlob) then
            Error(GetLastErrorText());

        AttachmentName := CopyStr(StrSubstNo('Factura_%1.pdf', PostedInvoice."No."), 1, MaxStrLen(AttachmentName));
        EmailSubject := CopyStr(StrSubstNo('PRUEBA INTERNA | MTM Logix | Factura electronica %1', PostedInvoice."No."), 1, MaxStrLen(EmailSubject));
        EmailBody := BuildCommandEraEmailBody(PostedInvoice, Customer);
        if not TryPrepareInvoiceEmail(
            PostedInvoice,
            AttachmentBlob,
            AttachmentName,
            EmailSubject,
            EmailBody,
            TestRecipientLbl,
            MessageId)
        then
            Error(GetLastErrorText());

        if not TrySendInvoiceEmail(MessageId, SenderAccount) then
            Error(GetLastErrorText());

        if not HasNativeSentEmailEvidence(
            PostedInvoice,
            MessageId,
            SenderAccount."Account Id",
            EvidenceError)
        then begin
            if EvidenceError = '' then
                EvidenceError := StrSubstNo(
                    'Business Central accepted internal canary message %1 for invoice %2, but its exact native Sent Email record was not found.',
                    MessageId,
                    PostedInvoice."No.");
            Error(EvidenceError);
        end;
    end;

    procedure GetApprovedInvoiceTestEmailEvidence(PostedInvoice: Record "Sales Invoice Header"): Text
    var
        EmailOutbox: Record "Email Outbox" temporary;
        SenderAccount: Record "Email Account" temporary;
        SentEmail: Record "Sent Email" temporary;
        Email: Codeunit Email;
        EvidenceError: Text;
        ExpectedSubject: Text[250];
        MessageId: Guid;
        SenderEvidence: Text;
    begin
        if not ResolveRequiredSenderAccount(SenderAccount, EvidenceError) then
            exit('ConfigurationError|' + EvidenceError);

        SenderEvidence := BuildSenderEvidence(SenderAccount);

        ExpectedSubject := CopyStr(
            StrSubstNo('PRUEBA INTERNA | MTM Logix | Factura electronica %1', PostedInvoice."No."),
            1,
            MaxStrLen(ExpectedSubject));

        Email.GetSentEmailsForRecord(Database::"Sales Invoice Header", PostedInvoice.SystemId, SentEmail);
        if SentEmail.FindSet() then
            repeat
                MessageId := SentEmail.GetMessageId();
                if IsMatchingInternalCanaryMessage(MessageId, ExpectedSubject) then begin
                    if SentEmail.GetAccountId() <> SenderAccount."Account Id" then
                        exit(StrSubstNo('SentWrongAccount|MessageId=%1|%2', MessageId, SenderEvidence));
                    exit(StrSubstNo('Sent|MessageId=%1|Recipient=%2|%3', MessageId, TestRecipientLbl, SenderEvidence));
                end;
            until SentEmail.Next() = 0;

        Email.GetEmailOutboxForRecord(PostedInvoice, EmailOutbox);
        if EmailOutbox.FindSet() then
            repeat
                MessageId := EmailOutbox.GetMessageId();
                if IsMatchingInternalCanaryMessage(MessageId, ExpectedSubject) then
                    exit(
                        StrSubstNo(
                            'Outbox|MessageId=%1|Status=%2|Recipient=%3',
                            MessageId,
                            Format(Email.GetOutboxEmailRecordStatus(MessageId)),
                            TestRecipientLbl) + '|' + SenderEvidence + '|' + BuildOutboxEvidence(EmailOutbox));
            until EmailOutbox.Next() = 0;

        exit('NotFound|' + SenderEvidence);
    end;

    local procedure BuildSenderEvidence(SenderAccount: Record "Email Account" temporary): Text
    begin
        exit(
            StrSubstNo(
                'Sender=%1|AccountId=%2|Connector=%3|AccountName=%4',
                SenderAccount."Email Address",
                SenderAccount."Account Id",
                Format(SenderAccount.Connector),
                SenderAccount.Name));
    end;

    local procedure BuildOutboxEvidence(EmailOutbox: Record "Email Outbox" temporary): Text
    var
        OutboxRef: RecordRef;
        ErrorMessage: Text;
        SendFrom: Text;
        DateFailed: Text;
    begin
        OutboxRef.GetTable(EmailOutbox);
        ErrorMessage := ReadTextField(OutboxRef, 'Error Message');
        ErrorMessage := ErrorMessage.Replace('|', '/').Replace('\r', ' ').Replace('\n', ' ');
        SendFrom := ReadTextField(OutboxRef, 'Send From');
        DateFailed := ReadTextField(OutboxRef, 'Date Failed');
        exit(StrSubstNo('SendFrom=%1|DateFailed=%2|ProviderError=%3', SendFrom, DateFailed, ErrorMessage));
    end;

    local procedure GetSendFailureEvidence(
        PostedInvoice: Record "Sales Invoice Header";
        MessageId: Guid;
        SendError: Text): Text
    var
        EmailOutbox: Record "Email Outbox" temporary;
        Email: Codeunit Email;
    begin
        Email.GetEmailOutboxForRecord(PostedInvoice, EmailOutbox);
        if EmailOutbox.FindSet() then
            repeat
                if EmailOutbox.GetMessageId() = MessageId then
                    exit(SendError + ' | ' + BuildOutboxEvidence(EmailOutbox));
            until EmailOutbox.Next() = 0;

        exit(SendError);
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
    begin
        if not HasNativeSentEmailEvidence(
            PostedInvoice,
            Audit."BC Email Message Id",
            Audit."Sender Account Id",
            EvidenceError)
        then
            exit(false);

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

    local procedure HasNativeSentEmailEvidence(
        PostedInvoice: Record "Sales Invoice Header";
        MessageId: Guid;
        SenderAccountId: Guid;
        var EvidenceError: Text): Boolean
    var
        SentEmail: Record "Sent Email" temporary;
        Email: Codeunit Email;
    begin
        EvidenceError := '';
        if IsNullGuid(MessageId) then
            exit(false);

        Email.GetSentEmailsForRecord(Database::"Sales Invoice Header", PostedInvoice.SystemId, SentEmail);
        if not SentEmail.FindSet() then
            exit(false);

        repeat
            if SentEmail.GetMessageId() = MessageId then begin
                if SentEmail.GetAccountId() <> SenderAccountId then begin
                    EvidenceError := StrSubstNo(
                        'Native Sent Email evidence for message %1 used an unexpected Business Central sender account.',
                        MessageId);
                    exit(false);
                end;
                exit(true);
            end;
        until SentEmail.Next() = 0;

        exit(false);
    end;

    local procedure IsMatchingInternalCanaryMessage(MessageId: Guid; ExpectedSubject: Text): Boolean
    var
        EmailMessage: Codeunit "Email Message";
        Recipient: Text;
        ToRecipients: List of [Text];
    begin
        if not EmailMessage.Get(MessageId) then
            exit(false);
        if EmailMessage.GetSubject() <> ExpectedSubject then
            exit(false);

        EmailMessage.GetRecipients(Enum::"Email Recipient Type"::"To", ToRecipients);
        foreach Recipient in ToRecipients do
            if LowerCase(Recipient) = LowerCase(TestRecipientLbl) then
                exit(true);

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
        PostedInvoice.SetRecFilter();
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
            '<tr><td style="background:#F7F5EF;padding:20px 32px;">' +
            '<img src="' + LogoUrlLbl + '" width="238" height="58" alt="MTM Logix" style="display:block;width:238px;max-width:100%;height:auto;border:0;outline:none;text-decoration:none;"></td></tr>' +
            '<tr><td style="background:#050B2E;padding:22px 32px;border-bottom:5px solid #C9A24A;">' +
            '<div style="color:#FFFFFF;font-size:24px;font-weight:700;">FACTURA ELECTRONICA</div></td></tr>' +
            '<tr><td style="padding:32px;font-size:15px;line-height:1.55;">' +
            '<p style="margin:0 0 16px;">Estimado/a ' + EscapeHtml(Customer.Name) + ',</p>' +
            '<p style="margin:0 0 16px;">Adjuntamos la factura electronica <strong>' + EscapeHtml(PostedInvoice."No.") +
            '</strong>. El PDF adjunto contiene el detalle y las referencias operativas del embarque.</p>' +
            '<p style="margin:24px 0 0;">Atentamente,<br><strong>Consuelo Velasquez</strong><br>MTM Logix<br>' + ExpectedSenderLbl + '</p>' +
            '</td></tr><tr><td style="padding:18px 32px;background:#F7F5EF;border-top:1px solid #D9D5CA;color:#5E6474;font-size:12px;">' +
            'Beyond Visibility. Into Command.</td></tr></table></td></tr></table></body></html>');
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
