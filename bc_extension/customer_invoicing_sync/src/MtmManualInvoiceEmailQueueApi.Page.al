page 71017 "MTM Manual Inv Email Queue API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'invoiceSync';
    APIVersion = 'v1.0';
    EntityName = 'manualInvoiceEmailQueueEntry';
    EntitySetName = 'manualInvoiceEmailQueueEntries';
    SourceTable = "MTM Manual Inv Email Queue";
    ODataKeyFields = "Posted Invoice System Id";
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions = tabledata "MTM Manual Inv Email Queue" = R;

    layout
    {
        area(Content)
        {
            repeater(General)
            {
                field(postedInvoiceId; Rec."Posted Invoice System Id") { Caption = 'Posted Invoice Id'; }
                field(postedInvoiceNumber; Rec."Posted Invoice No.") { Caption = 'Posted Invoice Number'; }
                field(customerNumber; Rec."Customer No.") { Caption = 'Customer Number'; }
                field(externalDocumentNumber; Rec."External Document No.") { Caption = 'External Document Number'; }
                field(status; StatusTxt) { Caption = 'Status'; }
                field(enqueuedAt; Rec."Enqueued At") { Caption = 'Enqueued At'; }
                field(nextAttemptAt; Rec."Next Attempt At") { Caption = 'Next Attempt At'; }
                field(stampWaitDeadline; Rec."Stamp Wait Deadline") { Caption = 'Stamp Wait Deadline'; }
                field(stampCheckCount; Rec."Stamp Check Count") { Caption = 'Stamp Check Count'; }
                field(sendAttemptCount; Rec."Send Attempt Count") { Caption = 'Send Attempt Count'; }
                field(lastAttemptAt; Rec."Last Attempt At") { Caption = 'Last Attempt At'; }
                field(lastErrorText; Rec."Last Error Text") { Caption = 'Last Error Text'; }
                field(sentAt; Rec."Sent At") { Caption = 'Sent At'; }
                field(capturedBy; Rec."Captured By") { Caption = 'Captured By'; }
            }
        }
    }

    trigger OnAfterGetRecord()
    begin
        StatusTxt := Format(Rec.Status);
    end;

    var
        StatusTxt: Text[30];
}
