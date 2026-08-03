codeunit 71016 "MTM Manual Inv Email Worker"
{
    TableNo = "Job Queue Entry";
    Permissions =
        tabledata "MTM Manual Inv Email Setup" = R,
        tabledata "MTM Manual Inv Email Queue" = RIMD,
        tabledata "MTM Invoice Email Audit" = R,
        tabledata "Sales Invoice Header" = R;

    trigger OnRun()
    begin
        ProcessDueEntries();
    end;

    procedure ProcessDueEntries()
    var
        Queue: Record "MTM Manual Inv Email Queue";
        Setup: Record "MTM Manual Inv Email Setup";
        EntryId: Guid;
        ProcessedCount: Integer;
    begin
        if not Setup.Get('') then
            exit;
        if not Setup."Capture Enabled" then
            exit;

        while ProcessedCount < Setup."Maximum Entries Per Run" do begin
            Queue.Reset();
            Queue.SetCurrentKey(Status, "Next Attempt At");
            Queue.SetFilter(
                Status,
                '%1|%2|%3',
                Queue.Status::WaitingForStamp,
                Queue.Status::ReadyToSend,
                Queue.Status::Sending);
            Queue.SetFilter("Next Attempt At", '>%1&<=%2', 0DT, CurrentDateTime());
            if not Queue.FindFirst() then
                exit;

            EntryId := Queue."Posted Invoice System Id";
            ProcessEntry(EntryId, Setup);
            Commit();
            ProcessedCount += 1;
        end;
    end;

    procedure ResetForOperatorRetry(var Queue: Record "MTM Manual Inv Email Queue")
    begin
        if Queue.Status <> Queue.Status::ReviewRequired then
            Error(
                'Only Review Required entries may be reset. Invoice %1 is %2.',
                Queue."Posted Invoice No.",
                Format(Queue.Status));
        Queue.Status := Queue.Status::WaitingForStamp;
        Queue."Next Attempt At" := CurrentDateTime();
        Queue."Last Error Text" := '';
        Queue.Modify(true);
    end;

    local procedure ProcessEntry(EntryId: Guid; Setup: Record "MTM Manual Inv Email Setup")
    var
        Audit: Record "MTM Invoice Email Audit";
        PostedInvoice: Record "Sales Invoice Header";
        Queue: Record "MTM Manual Inv Email Queue";
        SendError: Text;
    begin
        Queue.LockTable();
        if not Queue.Get(EntryId) then
            exit;
        if (Queue."Next Attempt At" = 0DT) or (Queue."Next Attempt At" > CurrentDateTime()) then
            exit;
        if not (Queue.Status in [Queue.Status::WaitingForStamp, Queue.Status::ReadyToSend, Queue.Status::Sending]) then
            exit;

        if Queue.Status = Queue.Status::Sending then begin
            MarkReviewRequired(
                Queue,
                'El proceso anterior quedo en estado Sending sin confirmacion final. Revise MTM Invoice Email Audit y Sent Email antes de autorizar un reintento.');
            exit;
        end;

        if not PostedInvoice.GetBySystemId(EntryId) then begin
            MarkReviewRequired(Queue, 'La factura registrada ya no existe en Business Central.');
            exit;
        end;

        if PostedInvoice.Cancelled then begin
            Queue.Status := Queue.Status::Cancelled;
            Queue."Next Attempt At" := 0DT;
            Queue."Last Error Text" := 'La factura fue anulada antes del envio al cliente.';
            Queue.Modify(true);
            exit;
        end;

        if not IsStamped(PostedInvoice) then begin
            HandlePendingStamp(Queue, Setup);
            exit;
        end;

        if not Setup."Customer Send Enabled" then begin
            Queue.Status := Queue.Status::ReadyToSend;
            Queue."Next Attempt At" := 0DT;
            Queue."Last Error Text" := 'Factura timbrada y lista. El envio automatico al cliente esta deshabilitado.';
            Queue.Modify(true);
            exit;
        end;

        Queue.Status := Queue.Status::Sending;
        Queue."Send Attempt Count" += 1;
        Queue."Last Attempt At" := CurrentDateTime();
        Queue."Next Attempt At" := CurrentDateTime() + (15 * 60000);
        Queue."Last Error Text" := '';
        Queue.Modify(true);
        Commit();

        ClearLastError();
        if not TrySendApprovedInvoice(PostedInvoice) then begin
            SendError := GetLastErrorText();
            if SendError = '' then
                SendError := 'Business Central no devolvio detalle del error de envio.';
            Queue.Get(EntryId);
            MarkReviewRequired(Queue, 'Fallo el envio automatico al cliente: ' + SendError);
            exit;
        end;

        if not Audit.Get(EntryId) then begin
            Queue.Get(EntryId);
            MarkReviewRequired(Queue, 'El envio termino sin crear evidencia en MTM Invoice Email Audit.');
            exit;
        end;
        if (Audit.Status <> Audit.Status::Sent) or (not Audit."Native Sent Verified") then begin
            Queue.Get(EntryId);
            MarkReviewRequired(
                Queue,
                'Business Central acepto el proceso, pero no existe evidencia nativa verificada de Sent Email. No se reenviara automaticamente.');
            exit;
        end;

        Queue.Get(EntryId);
        Queue.Status := Queue.Status::Sent;
        Queue."Next Attempt At" := 0DT;
        Queue."Sent At" := Audit."Sent At";
        Queue."Last Error Text" := '';
        Queue.Modify(true);
    end;

    local procedure HandlePendingStamp(var Queue: Record "MTM Manual Inv Email Queue"; Setup: Record "MTM Manual Inv Email Setup")
    begin
        Queue."Stamp Check Count" += 1;
        Queue."Last Attempt At" := CurrentDateTime();
        if (Queue."Stamp Wait Deadline" <> 0DT) and (CurrentDateTime() >= Queue."Stamp Wait Deadline") then begin
            MarkReviewRequired(
                Queue,
                StrSubstNo(
                    'La factura %1 no recibio estado FEL Stamp Received dentro de %2 minutos.',
                    Queue."Posted Invoice No.",
                    Setup."Stamp Wait Timeout Minutes"));
            exit;
        end;

        Queue.Status := Queue.Status::WaitingForStamp;
        Queue."Next Attempt At" := CurrentDateTime() + (Setup."Poll Interval Minutes" * 60000);
        Queue."Last Error Text" := 'Esperando estado FEL Stamp Received.';
        Queue.Modify(true);
    end;

    local procedure MarkReviewRequired(var Queue: Record "MTM Manual Inv Email Queue"; ErrorText: Text)
    begin
        Queue.Status := Queue.Status::ReviewRequired;
        Queue."Next Attempt At" := 0DT;
        Queue."Last Error Text" := CopyStr(ErrorText, 1, MaxStrLen(Queue."Last Error Text"));
        Queue.Modify(true);
    end;

    [TryFunction]
    local procedure TrySendApprovedInvoice(PostedInvoice: Record "Sales Invoice Header")
    var
        InvoiceCustomerEmailMgt: Codeunit "MTM Invoice Customer Email Mgt";
    begin
        InvoiceCustomerEmailMgt.SendApprovedInvoiceEmail(PostedInvoice);
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
