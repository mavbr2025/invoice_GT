page 71016 "MTM Manual Inv Email Setup API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'invoiceSync';
    APIVersion = 'v1.0';
    EntityName = 'manualInvoiceEmailSetup';
    EntitySetName = 'manualInvoiceEmailSetups';
    SourceTable = "MTM Manual Inv Email Setup";
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;
    Permissions = tabledata "MTM Manual Inv Email Setup" = R;

    layout
    {
        area(Content)
        {
            repeater(General)
            {
                field(id; Rec.SystemId) { Caption = 'Id'; Editable = false; }
                field(captureEnabled; Rec."Capture Enabled") { Caption = 'Capture Enabled'; Editable = false; }
                field(customerSendEnabled; Rec."Customer Send Enabled") { Caption = 'Customer Send Enabled'; Editable = false; }
                field(pollIntervalMinutes; Rec."Poll Interval Minutes") { Caption = 'Poll Interval Minutes'; Editable = false; }
                field(stampWaitTimeoutMinutes; Rec."Stamp Wait Timeout Minutes") { Caption = 'Stamp Wait Timeout Minutes'; Editable = false; }
                field(initialDelaySeconds; Rec."Initial Delay Seconds") { Caption = 'Initial Delay Seconds'; Editable = false; }
                field(maximumEntriesPerRun; Rec."Maximum Entries Per Run") { Caption = 'Maximum Entries Per Run'; Editable = false; }
                field(lastActivatedAt; Rec."Last Activated At") { Caption = 'Last Activated At'; Editable = false; }
                field(lastActivatedBy; Rec."Last Activated By") { Caption = 'Last Activated By'; Editable = false; }
            }
        }
    }

    [ServiceEnabled]
    procedure PrepareCaptureOnly(var ActionContext: WebServiceActionContext)
    var
        SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
    begin
        SetupMgt.PrepareCaptureOnly();
        Rec.Get('');
        SetUpdatedResult(ActionContext);
    end;

    [ServiceEnabled]
    procedure EnableCustomerSend(var ActionContext: WebServiceActionContext)
    var
        SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
    begin
        SetupMgt.EnableCustomerSend();
        Rec.Get('');
        SetUpdatedResult(ActionContext);
    end;

    [ServiceEnabled]
    procedure DisableCustomerSend(var ActionContext: WebServiceActionContext)
    var
        SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
    begin
        SetupMgt.DisableCustomerSend();
        Rec.Get('');
        SetUpdatedResult(ActionContext);
    end;

    [ServiceEnabled]
    procedure DisableAll(var ActionContext: WebServiceActionContext)
    var
        SetupMgt: Codeunit "MTM Manual Inv Email Setup Mgt";
    begin
        SetupMgt.DisableAll();
        Rec.Get('');
        SetUpdatedResult(ActionContext);
    end;

    [ServiceEnabled]
    procedure ProcessDueEntries(var ActionContext: WebServiceActionContext)
    var
        Worker: Codeunit "MTM Manual Inv Email Worker";
    begin
        Worker.ProcessDueEntries();
        SetUpdatedResult(ActionContext);
    end;

    local procedure SetUpdatedResult(var ActionContext: WebServiceActionContext)
    begin
        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM Manual Inv Email Setup API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;
}
